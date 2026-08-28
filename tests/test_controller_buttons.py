#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: test_controller_buttons.py
# PURPOSE: Unit tests for the maintenance page command buttons in
#          GeneratorController (built in buttons and buttons imported via the
#          "import_buttons" config file entry).
#
# USAGE: from the root of the repository:
#           python -m unittest discover -s tests
#
# -------------------------------------------------------------------------------

import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genmonlib.controller import GeneratorController

# name of a button import file that ships with genmon in data/commands
IMPORT_FILE = "example_button.json"
IMPORT_BUTTON_NAME = "testexamplebutton"

BUILT_IN_BUTTON = {
    "onewordcommand": "builtinbutton",
    "title": "Built In Button",
    "command_sequence": [{"reg": "0001", "reg_type": "holding", "value": "0001"}],
}


class ButtonTestController(GeneratorController):
    """Minimal controller that exercises the button methods of the base class.

    The base class __init__ requires a config file, serial port, etc, so it is
    intentionally not called here. Only the attributes used by the button code
    are set up, which lets each test define the exact state under test.
    """

    NOT_SET = object()

    def __init__(
        self, buttons=NOT_SET, import_file_list=NOT_SET, imported_buttons=NOT_SET
    ):
        # note: GeneratorController.__init__ is not called on purpose, see above
        self.Errors = []
        if buttons is not self.NOT_SET:
            self.Buttons = buttons
        if import_file_list is not self.NOT_SET:
            self.ImportButtonFileList = import_file_list
        if imported_buttons is not self.NOT_SET:
            self.ImportedButtons = imported_buttons

    def LogError(self, Message):
        self.Errors.append(Message)

    def LogErrorLine(self, Message):
        self.Errors.append(Message)


def MakeController(buttons=None, import_file_list=None):
    return ButtonTestController(
        buttons=buttons, import_file_list=import_file_list, imported_buttons=[]
    )


def ButtonNames(button_list):
    return [button["onewordcommand"] for button in button_list]


class TestGetButtons(unittest.TestCase):
    def test_no_built_in_and_no_imported_buttons(self):
        # no built in buttons and nothing imported: nothing to display
        controller = MakeController(buttons=[], import_file_list=[])

        self.assertEqual(controller.GetButtons(), [])
        self.assertEqual(controller.Errors, [])

    def test_built_in_buttons_only(self):
        # existing behavior must be unchanged when nothing is imported
        controller = MakeController(
            buttons=[dict(BUILT_IN_BUTTON)], import_file_list=[]
        )

        self.assertEqual(ButtonNames(controller.GetButtons()), ["builtinbutton"])
        self.assertEqual(controller.Errors, [])

    def test_imported_buttons_only(self):
        # this is the bug being fixed: a controller with no built in buttons
        # must still return the buttons listed in import_buttons
        controller = MakeController(buttons=[], import_file_list=[IMPORT_FILE])

        self.assertEqual(ButtonNames(controller.GetButtons()), [IMPORT_BUTTON_NAME])
        self.assertEqual(controller.Errors, [])

    def test_built_in_and_imported_buttons(self):
        controller = MakeController(
            buttons=[dict(BUILT_IN_BUTTON)], import_file_list=[IMPORT_FILE]
        )

        self.assertEqual(
            ButtonNames(controller.GetButtons()), ["builtinbutton", IMPORT_BUTTON_NAME]
        )
        self.assertEqual(controller.Errors, [])

    def test_imported_buttons_stable_across_calls(self):
        # the imported buttons are only loaded once, repeated calls (the web app
        # calls this on every page load) must return the same list
        controller = MakeController(
            buttons=[dict(BUILT_IN_BUTTON)], import_file_list=[IMPORT_FILE]
        )

        first = ButtonNames(controller.GetButtons())
        second = ButtonNames(controller.GetButtons())

        self.assertEqual(first, ["builtinbutton", IMPORT_BUTTON_NAME])
        self.assertEqual(first, second)

    def test_imported_buttons_only_stable_across_calls(self):
        # Evolution air-cooled leaves self.Buttons empty. The first
        # start_info_json (genserv startup) must not starve later calls
        # (browser page load) of the imported buttons.
        controller = MakeController(buttons=[], import_file_list=[IMPORT_FILE])

        first = ButtonNames(controller.GetButtons())
        second = ButtonNames(controller.GetButtons())

        self.assertEqual(first, [IMPORT_BUTTON_NAME])
        self.assertEqual(first, second)
        self.assertEqual(controller.Buttons, [])

    def test_single_button_lookup_of_imported_button(self):
        # SetCommandButton() looks up a single button by name, an imported
        # button must be found for a controller with no built in buttons
        controller = MakeController(buttons=[], import_file_list=[IMPORT_FILE])

        button = controller.GetButtons(singlebuttonname=IMPORT_BUTTON_NAME)

        self.assertTrue(isinstance(button, dict))
        self.assertEqual(button["onewordcommand"], IMPORT_BUTTON_NAME)

    def test_single_imported_button_lookup_after_list_fetch(self):
        # start_info_json loads the full list first; a later click must still
        # find the imported button by name
        controller = MakeController(buttons=[], import_file_list=[IMPORT_FILE])

        self.assertEqual(ButtonNames(controller.GetButtons()), [IMPORT_BUTTON_NAME])
        button = controller.GetButtons(singlebuttonname=IMPORT_BUTTON_NAME)

        self.assertTrue(isinstance(button, dict))
        self.assertEqual(button["onewordcommand"], IMPORT_BUTTON_NAME)

    def test_missing_import_file_is_ignored(self):
        controller = MakeController(
            buttons=[], import_file_list=["does_not_exist.json"]
        )

        self.assertEqual(controller.GetButtons(), [])
        self.assertEqual(len(controller.Errors), 1)


class TestButtonsUninitialized(unittest.TestCase):
    """The button attributes can be None or, if there is no config object,
    never assigned at all. None of that may raise."""

    def test_both_none(self):
        controller = MakeController(buttons=None, import_file_list=None)

        self.assertEqual(controller.GetButtons(), [])
        self.assertEqual(controller.Errors, [])

    def test_buttons_none_with_imported_buttons(self):
        controller = MakeController(buttons=None, import_file_list=[IMPORT_FILE])

        self.assertEqual(ButtonNames(controller.GetButtons()), [IMPORT_BUTTON_NAME])
        self.assertEqual(controller.Errors, [])

    def test_import_file_list_none_with_built_in_buttons(self):
        controller = MakeController(
            buttons=[dict(BUILT_IN_BUTTON)], import_file_list=None
        )

        self.assertEqual(ButtonNames(controller.GetButtons()), ["builtinbutton"])
        self.assertEqual(controller.Errors, [])

    def test_imported_buttons_attribute_none(self):
        controller = ButtonTestController(
            buttons=[], import_file_list=[IMPORT_FILE], imported_buttons=None
        )

        self.assertEqual(ButtonNames(controller.GetButtons()), [IMPORT_BUTTON_NAME])
        self.assertEqual(controller.Errors, [])

    def test_attributes_never_assigned(self):
        controller = ButtonTestController()

        self.assertEqual(controller.GetButtons(), [])
        self.assertEqual(controller.LoadButtonsFromFile(), [])
        self.assertEqual(controller.GetButtonsCommon(None), [])
        self.assertEqual(controller.Errors, [])

    def test_button_attributes_are_initialized_before_the_config_is_read(self):
        # the attributes are assigned before the "if self.config != None" block
        # so that they exist even when there is no config object
        source = inspect.getsource(GeneratorController.__init__)
        config_check = source.index("if self.config != None:")

        for name in ("Buttons", "ImportButtonFileList", "ImportedButtons"):
            assignment = "self." + name + " = []"
            self.assertIn(assignment, source)
            self.assertLess(source.index(assignment), config_check, name)


if __name__ == "__main__":
    unittest.main()
