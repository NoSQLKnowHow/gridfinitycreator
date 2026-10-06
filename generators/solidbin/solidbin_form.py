from flask_wtf import FlaskForm
from wtforms import IntegerField, DecimalField, SelectField, BooleanField
from wtforms.widgets import NumberInput
from grid_constants import *
import os
import help_provider as help
from generators.common.settings_form import get_standard_settings_form
from generators.common.validators import Bounded

class Form(FlaskForm):
    id = "solidbin"
    sizeUnitsX     = IntegerField("Width", validators=[Bounded(1, Grid.MAX_GRID_UNITS)], default=2)
    sizeUnitsY     = IntegerField("Length", validators=[Bounded(1, Grid.MAX_GRID_UNITS)], default=2)
    sizeUnitsZ     = IntegerField("Height", validators=[Bounded(1, Grid.MAX_HEIGHT_UNITS)], default=6)
    # Defaults must be real booleans: a string such as "False" is non-empty and
    # therefore truthy, which rendered those switches as checked
    addStackingLip = BooleanField("Stacking lip", default=True)
    addMagnetHoles = BooleanField("Magnet holes", default=True)
    magnetHoleDiameter = DecimalField("Magnet-hole diameter", validators=[Bounded(1, 10)], default = 6.5, places = 2)
    addRemovalHoles = BooleanField("Magnet removal holes", default=False)
    addScrewHoles   = BooleanField("Screw holes", default=False)
    exportFormat    = SelectField('Export format', choices=[('stl', 'STL'), ('step', 'STEP'), ('3mf', '3MF')])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sizeUnitsX.description = help.get_size_help()
        self.sizeUnitsY.description = help.get_size_help()
        self.sizeUnitsZ.description = help.get_size_help()
        self.addStackingLip.description = help.get_stackinglip_help()
        self.addMagnetHoles.description = help.get_magnet_help()
        self.magnetHoleDiameter.description = help.get_magnet_help()
        self.addRemovalHoles.description = help.get_magnet_help()
        self.addScrewHoles.description = help.get_magnet_help()
        self.exportFormat.description = help.get_exportformat_help()

    def get_rows(self):
        return [
          ["Size", [self.sizeUnitsX, self.sizeUnitsY, self.sizeUnitsZ]],
          ["Magnets", [self.addMagnetHoles, self.addRemovalHoles, self.addScrewHoles, self.magnetHoleDiameter]],
          ["Other", [self.addStackingLip, self.exportFormat]],
        ]
    
    def get_title(self):
        return "Solid bin"
    
    def get_settings_html(self):
        return get_standard_settings_form()

    def get_description(self):
        with open(os.path.dirname(__file__) + '/solidbin_description.html', 'r') as reader:
            return reader.read()    
        
