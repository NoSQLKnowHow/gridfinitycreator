from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, BooleanField, HiddenField
from wtforms.widgets import NumberInput
from grid_constants import *
import os
import help_provider as help
from generators.common.settings_form import get_standard_settings_form

class Form(FlaskForm):
    id = "lightbin"
    sizeUnitsX     = IntegerField("Width", widget=NumberInput(min = 1, max = Grid.MAX_GRID_UNITS), default=2)
    sizeUnitsY     = IntegerField("Length", widget=NumberInput(min = 1, max = Grid.MAX_GRID_UNITS), default=2)
    sizeUnitsZ     = IntegerField("Height", widget=NumberInput(min = 1, max = Grid.MAX_HEIGHT_UNITS), default=6)
    compartmentsX  = IntegerField("Width direction", widget=NumberInput(min = 1, max = Grid.MAX_COMPARTMENTS_PER_GRID_UNIT*Grid.MAX_GRID_UNITS), default=1)
    compartmentsY  = IntegerField("Length direction", widget=NumberInput(min = 1, max = Grid.MAX_COMPARTMENTS_PER_GRID_UNIT*Grid.MAX_GRID_UNITS), default=1)
    addStackingLip = BooleanField("Stacking lip", default="True")
    addLabelRidge  = BooleanField("Add label tab", default="True", false_values=(False, "false", ""))
    exportFormat   = SelectField('Export format', choices=[('stl', 'STL'), ('step', 'STEP'), ('3mf', '3MF')])
    removedWalls   = HiddenField(default="")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sizeUnitsX.description = help.get_size_help()
        self.sizeUnitsY.description = help.get_size_help()
        self.sizeUnitsZ.description = help.get_size_help()
        self.compartmentsX.description = help.get_compartment_help()
        self.compartmentsY.description = help.get_compartment_help()
        self.addStackingLip.description = help.get_stackinglip_help()
        self.exportFormat.description = help.get_exportformat_help()
        self.addLabelRidge.description = help.get_labeltab_help()

    def has_layout_editor(self):
        return True

    def get_rows(self):
        return [
            ["Size", [self.sizeUnitsX, self.sizeUnitsY, self.sizeUnitsZ]],
            ["Compartments", [self.compartmentsX, self.compartmentsY]],
            ["Options", [self.addStackingLip, self.addLabelRidge, self.exportFormat]],
        ]
    
    def get_title(self):
        return "Light bin"
    
    def get_settings_html(self):
        return get_standard_settings_form()

    def get_description(self):
        with open(os.path.dirname(__file__) + '/lightbin_description.html', 'r') as reader:
            return reader.read()       
