#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: mycrypto.py
# PURPOSE: AES Encyption using python cryptography module 
#
#  AUTHOR: Jason G Yates
#    DATE: 08-23-2020
#
# MODIFICATIONS:
#
# USAGE:
#
#-------------------------------------------------------------------------------

import os, sys
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


from genmonlib.mycommon import MyCommon
from genmonlib.program_defaults import ProgramDefaults

#------------ MyCrypto class -------------------------------------------------
class MyCrypto(MyCommon):

    #------------ MyCrypto::init------------------------------------------------
    def __init__(self, log = None, console = None, key = None, iv = None):
        self.log = log
        self.console = console
        self.key = key          # bytes
        self.iv = iv            # bytes
        self.keysize = len(key) # in bytes
        self.blocksize = len(key) # in bytes

        self.debug = False
        # presently only AES-128 CBC mode is supported
        if self.keysize != 16:
            self.LogError("MyCrypto: WARNING: key size not 128: " + str(self.keysize))

        if len(self.iv) != 16:
            self.LogError("MyCrypto: WARNING: iv size not 128: " + str(self.keysize))
        try:
            self.backend = default_backend()
            self.cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), backend=self.backend)
            self.decryptor = self.cipher.decryptor()
            self.encryptor = self.cipher.encryptor()

        except Exception as e1:
            self.LogErrorLine("Error in MyCrypto:init: " + str(e1))
            sys.exit(1)
    #------------ MyCrypto::Encrypt---------------------------------------------
    # one block encrypt
    def Encrypt(self, cleartext, finalize = True):
        try:
            if len(cleartext) != self.keysize:
                self.LogError("MyCrypto:Encrypt: Blocksize mismatch: %d, %d" % (len(cyptertext), self.keysize))
                return None
            if finalize:
                retval =  self.encryptor.update(cleartext) + self.encryptor.finalize()
                self.Restart()
                return retval
            else:
                return self.encryptor.update(cleartext)
        except Exception as e1:
            self.LogErrorLine("Error in MyCrypto:Encrypt: " + str(e1))
            return None
    #------------ MyCrypto::Decrypt---------------------------------------------
    # one block decrypt
    def Decrypt(self, cyptertext, finalize = True):

        try:
            if len(cyptertext) != self.keysize:
                self.LogError("MyCrypto:Decrypt: Blocksize mismatch: %d, %d" % (len(cyptertext), self.keysize))
                return None

            if finalize:
                retval =  self.decryptor.update(cyptertext) + self.decryptor.finalize()
                self.Restart()
                return retval
            else:
                return self.decryptor.update(cyptertext)
        except Exception as e1:
            self.LogErrorLine("Error in MyCrypto:Decrypt: " + str(e1))
            return None

    #------------ MyCrypto::Restart---------------------------------------------
    def Restart(self, key = None, iv = None):

        try:
            if key != None:
                self.key = key
            if iv != None:
                self.iv = iv
            self.cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), backend=self.backend)
            self.decryptor = self.cipher.decryptor()
            self.encryptor = self.cipher.encryptor()
        except Exception as e1:
            self.LogErrorLine("Error in MyCrypto:Restart: " + str(e1))
            return None

    #------------ MyCrypto::EncryptBuff-----------------------------------------
    # multiple block encrypt
    def EncryptBuff(self, plaintext_buff, pad_zero = True):
        try:

            if plaintext_buff == None:
                self.LogError("MyCrypto:EncryptBuff: Error: invalid buffer! ")
                return None
            if len(plaintext_buff) == 0:
                self.LogError("MyCrypto:EncryptBuff: Warning: plaintext buffer size is invalid")
                return None

            if len(plaintext_buff) % self.blocksize:
                self.LogDebug("MyCrypto:EncryptBuff: WARNING: buffer is not a multipe of blocksize")
            index1 = 0
            index2 = self.blocksize
            ct_buf = b""
            while(True):
                if index2 > len(plaintext_buff):
                    # remaining bytes are not block size
                    buff = plaintext_buff[index1:]
                    if pad_zero:
                        for i in range(0,(self.blocksize - len(buff))):
                            buff += b'\0'
                        ct_buf += self.Encrypt(buff)
                        break
                    else:
                        # append plain text to cryptotext buffer
                        ct_buf += buff
                    break
                buff = plaintext_buff[index1:index2]
                ct_buf += self.Encrypt(buff)
                index1 += self.blocksize
                index2 += self.blocksize
                if index1 == len(plaintext_buff):
                    break
            return ct_buf

        except Exception as e1:
            self.LogErrorLine("Error in MyCrypto:EncryptBuff: " + str(e1))
            return None

    #------------ MyCrypto::DecryptBuff-----------------------------------------
    # multiple block decrypt
    def DecryptBuff(self, crypttext_buff, pad_zero = True):
        try:

            if crypttext_buff == None:
                self.LogError("MyCrypto:DecryptBuff: Error: invalid buffer! ")
                return None
            if len(crypttext_buff) < self.blocksize:
                self.LogError("MyCrypto:DecryptBuff: Error: crypttext buffer size less than blocksize")
                return None

            if len(crypttext_buff) % self.blocksize:
                self.LogDebug("MyCrypto:DecryptBuff: WARNING: buffer is not a multipe of blocksize")

            index1 = 0
            index2 = self.blocksize
            pt_buf = b""
            while(True):
                if index2 > len(crypttext_buff):
                    # remaining bytes are not block size
                    buff = crypttext_buff[index1:]
                    if pad_zero:
                        for i in range(0,(self.blocksize - len(buff))):
                            buff += b'\0'
                        pt_buf += self.Decrypt(buff)
                        break
                    else:
                        # append plain text to cryptotext buffer
                        pt_buf += buff
                    break
                buff = crypttext_buff[index1:index2]
                pt_buf += self.Decrypt(buff)
                index1 += self.blocksize
                index2 += self.blocksize
                if index1 == len(crypttext_buff):
                    break

            return pt_buf

        except Exception as e1:
            self.LogErrorLine("Error in MyCrypto:EncryptBuff: " + str(e1))
            return None
