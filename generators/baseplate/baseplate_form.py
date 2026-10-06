from flask_wtf import FlaskForm
from wtforms import IntegerField, DecimalField, SelectField, BooleanField
from wtforms.widgets import NumberInput
from grid_constants import *
import os
import help_provider as help
from generators.common.settings_form import get_standard_settings_form

class Form(FlaskForm):
    id = "baseplate"
    sizeUnitsX     = IntegerField("Width", widget=NumberInput(min = 1, max = Grid.MAX_GRID_UNITS), default=2)
    sizeUnitsY     = IntegerField("Length", widget=NumberInput(min = 1, max = Grid.MAX_GRID_UNITS), default=2)
    baseStyle      = SelectField('Base style', choices=[
                        ('standard', 'Frame only'),
                        ('solid', 'Solid'),
                        ('skeleton', 'Skeletonized'),
                        ('weighted', 'Weighted'),
                    ], default='standard')
    baseThickness  = DecimalField("Base thickness", default = 2.4, places = 2)
    addMagnetHoles = BooleanField("Magnet holes", false_values=(False, "false", ""))
    magnetHoleDiameter = DecimalField("Magnet-hole diameter", default = 6.5, places = 2)
    addScrewHoles  = BooleanField("Screw holes", false_values=(False, "false", ""))
    exportFormat   = SelectField('Export format', choices=[('stl', 'STL'), ('step', 'STEP'), ('3mf', '3MF')])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sizeUnitsX.description = help.get_size_help()
        self.sizeUnitsY.description = help.get_size_help()
        self.baseStyle.description = help.get_baseplate_style_help()
        self.baseThickness.description = help.get_baseplate_style_help()
        self.addMagnetHoles.description = help.get_magnet_help()
        self.magnetHoleDiameter.description = help.get_magnet_help()
        self.addScrewHoles.description = help.get_baseplate_style_help()
        self.exportFormat.description = help.get_exportformat_help()

    def get_rows(self):
        return [
            ["Size", [self.sizeUnitsX, self.sizeUnitsY]],
            ["Base", [self.baseStyle, self.baseThickness]],
            ["Magnets & screws", [self.addMagnetHoles, self.magnetHoleDiameter, self.addScrewHoles]],
            ["Options", [self.exportFormat]],
        ]

    def get_settings_html(self):
        return get_standard_settings_form()

    def get_title(self):
        return "Baseplate"

    def get_description(self):
        with open(os.path.dirname(__file__) + '/baseplate_description.html', 'r') as reader:
            return reader.read()
