from dataclasses import dataclass

# Generator inputs
@dataclass
class Settings:
    sizeUnitsX: int = 2 # Width (X) of the baseplate in grid units
    sizeUnitsY: int = 2 # Length (Y) of the baseplate in grid units

    # Style of the plate below the grid frame:
    #   standard - just the frame profile, no base underneath (original design)
    #   solid    - frame on a solid slab
    #   skeleton - frame on a slab with a large round cutout per cell to save plastic
    #   weighted - frame on a thicker slab with underside pockets for weights (steel/sand/BBs)
    baseStyle: str = "standard"
    baseThickness: float = 2.4 # Thickness of the slab below the frame (mm)

    addMagnetHoles: bool = False    # Add magnet holes to each grid cell corner
    magnetHoleDiameter: float = 6.5 # Diameter of magnet holes
    addScrewHoles: bool = False     # Add countersunk mounting screw holes at each cell center

    exportFormat: str = "stl"
