//

import java.net.Socket;
import java.io.*;
import java.util.logging;

//-------------------------------------------------------------------------------
// Class ClientInterface
//-------------------------------------------------------------------------------
public class ClientInterface {


    private String m_EndOfMessage = "EndOfMessage";
    private int m_rxdatasize = 2000;
    private String m_host = "";
    private int m_port = 0;
    private netAddress m_ServerAddress;
    private Socket m_Socket;
    private DataInputStream m_input;
    private DataOutputStream m_output;
    private m_netAddress m_ServerAddress;

    // setup logger
    private static final Logger m_Logger = Logger.getLogger( ClassName.class.getName() );

    private class CustomReturn {
        public String data;
        public boolean RetVal;
    }
    //-------------------------------------------------------------------------------
    // constructor
    //-------------------------------------------------------------------------------
    public ClientInterface(String newHost, int newPort) {

        m_host = newHost;
        m_port = newPort;
        Connect();
    }

    //-------------------------------------------------------------------------------
    // ClientInterface::Connect
    //-------------------------------------------------------------------------------
    private void Connect() {

        CustomReturn RetValues;

        try {
            m_ServerAddress = InetAddress.getByName(m_host);
            m_Socket = new Socket(m_netAddress, m_port);
            m_input = new DataInputStream(m_Socket.getInputStream());
            m_output = new DataOutputStream(m_Socket.getOutputStream());
            // Get initial status before commands are sent
            RetValues = Receive(true);
        }
        catch (Exception e) {
            FatalError(e.getMessage());
        }
    }

    //-------------------------------------------------------------------------------
    // ClientInterface::SendCommand
    //-------------------------------------------------------------------------------
    private void SendCommand(String cmd) {

        try{
            m_output.writeBytes(cmd);
        }
        catch (Exception e){
            String Message = "Error: TX:";
            Message.concat(e.getMessage());
            LogError( Message );
            Close();
            Connect();
        }
    }

    //-------------------------------------------------------------------------------
    // ClientInterface::Receive
    //-------------------------------------------------------------------------------
    private String Receive() {

        this.Receive(false);
    }

    //-------------------------------------------------------------------------------
    // ClientInterface::Receive
    //-------------------------------------------------------------------------------
    private CustomReturn Receive(boolean noeom) {

        byte[] messageByte = new byte[m_rxdatasize];
        int bytesRead;
        CustomReturn RetValues;

        RetValues.data = "";
        RetValues.RetVal =  true;

        try{
            bytesRead = m_input.read(messageByte);
            RetValues.data += new String(messageByte, 0, bytesRead);
            if (RetValues.data.length() != 0){
                if (!CheckForStarupMessage(RetValues.data) || !noeom){
                    while ( (RetValues.data.indexOf(m_EndOfMessage)) < 0){
                        bytesRead = m_input.read(messageByte);
                        String more = "";
                        more += new String(messageByte, 0, bytesRead);
                        if (more.length() != 0){
                            if (CheckForStarupMessage(more)){
                                RetValues.data = "";
                                RetValues.RetVal = false;
                                break;
                            }
                            RetValues.data = RetValues.data.concat(more);
                        }
                    }
                    if (RetValues.data.endsWith(m_EndOfMessage)){
                        RetValues.data = RetValues.data.substring(0, RetValues.data.length() - m_EndOfMessage.length());
                        RetValues.RetVal = true;
                    }
                }
            }
            else {
                Connect();
                RetValues.data = "";
                RetValues.RetVal = false;
                return RetValues;
            }
        }
        catch (Exception e){
            String Message = "Error: RX:";
            Message.concat(e.getMessage());
            LogError( Message );
            Close();
            Connect();
            RetValues.RetVal = false;
            RetValues.data = "Retry";
        }
        return RetValues;


    }

    //-------------------------------------------------------------------------------
    // ClientInterface::CheckForStarupMessage
    //-------------------------------------------------------------------------------
    private boolean CheckForStarupMessage(String data) {

        // check for initial status response from monitor
        if (data.startsWith("OK") || data.startsWith("CRITICAL:") || data.startsWith("WARNING:")){
            return true;
        }
        else{
            return false;
        }
    }

    //-------------------------------------------------------------------------------
    // ClientInterface:Close
    //-------------------------------------------------------------------------------
    public void Close() {
        m_output.close();
        m_input.close();
        m_Socket.close();
    }

    //-------------------------------------------------------------------------------
    // ClientInterface::ProcessMonitorCommand
    //-------------------------------------------------------------------------------
    public String ProcessMonitorCommand(String cmd){

        CustomReturn RetValues;
        RetValues.data = "";
        RetValues.RetVal = false;

        try{
            RetValues.RetVal = false;
            while (RetValues.RetVal == false){
                SendCommand(cmd);
                RetValues.data = Receive();
            }
        }
        catch (Exception e){
            String Message = "Error in ProcessMonitorCommand:";
            Message.concat(e.getMessage());
            LogError( Message );
        }
        return RetValues.data;

    }

    //-------------------------------------------------------------------------------
    // ClientInterface::LogError
    //-------------------------------------------------------------------------------
    private void LogError(String Message){
        m_Logger.log( Level.WARNING, Message );
    }

    //-------------------------------------------------------------------------------
    // ClientInterface::FatalError
    private void FatalError(String Message){
    //-------------------------------------------------------------------------------
        m_Logger.log( Level.SEVERE, Message );
    }

    public static void main(String[] args) {
        System.out.println("Hello World!"); // Display the string.
    }
}   // End ClientInterface class
