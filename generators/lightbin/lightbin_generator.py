import cadquery as cq
from cadquery import exporters
from grid_constants import *
import time
import logging

logger = logging.getLogger('LBG')

class Generator:
    def __init__(self, settings, grid) -> None:
        self.settings = settings
        self.grid = grid

        # Precalculate both before and after validation to process settings that changes
        self.precalculate()
        self.validate_settings()
        self.precalculate()

    def precalculate(self):
        """Precalculate a number of useful derived values used in construction"""
        self.brickSizeX = self.settings.sizeUnitsX * self.grid.GRID_UNIT_SIZE_X_MM - self.grid.BRICK_SIZE_TOLERANCE_MM 
        self.brickSizeY = self.settings.sizeUnitsY * self.grid.GRID_UNIT_SIZE_Y_MM - self.grid.BRICK_SIZE_TOLERANCE_MM
        self.brickSizeZ = self.settings.sizeUnitsZ*self.grid.HEIGHT_UNITSIZE_MM
        self.internalSizeX = self.brickSizeX-2*self.grid.WALL_THICKNESS
        self.internalSizeY = self.brickSizeY-2*self.grid.WALL_THICKNESS
        self.compartmentSizeX = self.internalSizeX / self.settings.compartmentsX
        self.compartmentSizeY = self.internalSizeY / self.settings.compartmentsY
        self.compartmentSizeZ = (self.settings.sizeUnitsZ-1)*self.grid.HEIGHT_UNITSIZE_MM # This is the height in units minus the thickness of the base

    def unit_base(self, basePlane):
        """Construct a 1x1 GridFinity unit base on the provided workplane"""

        x_offs = self.grid.BRICK_UNIT_SIZE_X/2-3.5
        frame_pts = [(0+x_offs,0),       (0+x_offs, 3.15), 
                    (1.6+x_offs, 4.75), (3.5+x_offs, 4.75),
                    (1.35+x_offs, 2.6), (1.35+x_offs, 0.8),
                    (0.55+x_offs, 0) 
                    ]

        path = basePlane.rect(self.grid.BRICK_UNIT_SIZE_X, self.grid.BRICK_UNIT_SIZE_X).val()
        path = path.fillet2D(self.grid.BASE_TOP_FILLET_RADIUS, path.Vertices())

        baseUnit = (
            cq.Workplane("XZ")
            .polyline(frame_pts)
            .close()
            .sweep(path)
            )

        floor = basePlane.box(self.grid.BRICK_UNIT_SIZE_X-6.7,self.grid.BRICK_UNIT_SIZE_X-6.7,self.settings.wallThickness).translate((0,0,self.settings.wallThickness/2))
        baseUnit = baseUnit.add(floor)
        baseUnit = baseUnit.combine()

        # Translate the result because it is now centered around the origin, which is inconvenient for subsequent steps
        baseUnit = baseUnit.translate((self.grid.BRICK_UNIT_SIZE_X/2, self.grid.BRICK_UNIT_SIZE_Y/2))

        return baseUnit

    def grid_base(self, basePlane):
        """Construct a base of WidthxLength grid units"""
        
        result = basePlane

        baseUnit = self.unit_base(basePlane)

        for x in range(self.settings.sizeUnitsX):
            for y in range(self.settings.sizeUnitsY):
                result.add(baseUnit.translate((x*self.grid.GRID_UNIT_SIZE_X_MM, y*self.grid.GRID_UNIT_SIZE_Y_MM, 0)))

        return result

    def brick_floor(self, basePlane):
        """Create a floor covering all unit bases"""

        # Create the solid floor
        floor = basePlane.box(self.grid.GRID_UNIT_SIZE_X_MM, self.grid.GRID_UNIT_SIZE_X_MM, self.grid.LIGHT_FLOOR_THICKNESS, centered = True, combine = False)

        # Create the cutout and remove it for each base unit
        cutoutSizeX = self.grid.BRICK_UNIT_SIZE_X-2*self.grid.WALL_THICKNESS
        cutoutSizeY = self.grid.BRICK_UNIT_SIZE_Y-2*self.grid.WALL_THICKNESS
        cutout = basePlane.box(cutoutSizeX, cutoutSizeY,3, centered = True, combine=False)
        cutout = cutout.edges("|Z")
        cutout = cutout.fillet(self.grid.CORNER_FILLET_RADIUS-self.grid.WALL_THICKNESS)
        
        floor = floor - cutout

        # Chamfer the sharp edges 
        dx = self.grid.BRICK_UNIT_SIZE_X/2
        dy = self.grid.BRICK_UNIT_SIZE_Y/2
        s = cq.selectors.BoxSelector((0,0,5), (dx,dy,6))
        floor = floor.edges(s).chamfer(self.grid.LIGHT_FLOOR_THICKNESS-self.grid.CHAMFER_EPSILON)
        floor = floor.translate((self.grid.BRICK_UNIT_SIZE_X/2, self.grid.BRICK_UNIT_SIZE_Y/2, self.grid.LIGHT_FLOOR_THICKNESS/2))

        result = basePlane
        for x in range(self.settings.sizeUnitsX):
            for y in range(self.settings.sizeUnitsY):
                result.add(floor.translate((x*self.grid.GRID_UNIT_SIZE_X_MM, y*self.grid.GRID_UNIT_SIZE_Y_MM, 0)))
        
        result = result.combine()
        
        # Create 
        plane = cq.Workplane("XY")
        cutout = plane.box(self.brickSizeX, self.brickSizeY, 1.9, centered=True, combine = False)
        cutout = cutout.edges("|Z").fillet(self.grid.CORNER_FILLET_RADIUS)
        shrink_box = plane.box(self.brickSizeX+5, self.brickSizeY+5, 1.9, centered = True, combine = False)
        shrink_box = shrink_box - cutout
        shrink_box = shrink_box.translate((self.brickSizeX/2, self.brickSizeY/2, 5.25))

        result = result - shrink_box
    
        return result

    def outer_wall(self, basePlane):
        """Create the outer wall of the bin"""
        
        plane = basePlane.workplane()
        sizeZ = self.compartmentSizeZ + self.grid.FLOOR_THICKNESS

        if self.settings.addStackingLip:
            sizeZ = sizeZ + self.grid.STACKING_LIP_HEIGHT

        wall = plane.box(self.brickSizeX, self.brickSizeY, sizeZ, combine = False)
        
        thickness = self.grid.WALL_THICKNESS
        wall = wall.edges("|Z").fillet(self.grid.CORNER_FILLET_RADIUS)

        cutout = (
                    plane.box(self.brickSizeX-2*thickness, self.brickSizeY-2*thickness, sizeZ, combine = False)
                )

        # If the walls are thicker than the outside radius of the corners, skip the fillet
        if thickness < self.grid.CORNER_FILLET_RADIUS:
            cutout = cutout.edges("|Z").fillet(self.grid.CORNER_FILLET_RADIUS-thickness)
        
        result = wall-cutout

        if self.settings.addStackingLip:
            result = result.edges(
                        cq.selectors.NearestToPointSelector((0, 0, sizeZ*2))
                    ).chamfer(thickness-self.grid.CHAMFER_EPSILON)
        
        result = result.translate((self.brickSizeX/2,self.brickSizeY/2,sizeZ/2-self.grid.LIGHT_FLOOR_THICKNESS))
            
        return result
    
    def divider_walls(self, basePlane):
        """Create a regularly spaced grid of internal divider walls"""

        resultPlane = basePlane.center(self.grid.WALL_THICKNESS, self.grid.WALL_THICKNESS)
        result = resultPlane.workplane()

        # basePlane sits at the top of the (thin) light-bin floor, whereas compartmentSizeZ
        # is derived assuming the standard FLOOR_THICKNESS. Stretch the divider height by the
        # difference so it still reaches the top of the interior wall (below the stacking lip),
        # while its untranslated bottom face rests flush on the floor.
        dividerHeight = self.compartmentSizeZ + self.grid.FLOOR_THICKNESS - self.grid.LIGHT_FLOOR_THICKNESS

        # The light floor is perforated with a weight-saving cutout per grid unit, so a divider
        # can span straight across a cutout and float with nothing beneath it. Every divider
        # gets a support plug filling the floor's own thickness below it (base top to floor
        # top) - this is always safe to add unconditionally, since the light floor tiles butt
        # up against each other seamlessly at every grid-unit seam, so this slice is solid
        # everywhere along a divider's length regardless of where it falls.
        upperSupportHeight = self.grid.LIGHT_FLOOR_THICKNESS

        # Below that, the base itself is mostly hollow (solid only right at the bottom and
        # around its outer taper), and adjacent units don't touch each other down there at all.
        # A deeper plug is needed to reach the bin's true bottom face and close the remaining
        # gap, but it must be clipped to wherever the base actually has material at z=0, or it
        # will bridge straight through the gaps between units and poke out past the bin's own
        # contour. Extrude the base's own bottom faces upward to build that footprint.
        lowerSupportHeight = self.baseTopZ
        footprintSolids = [
            cq.Solid.extrudeLinear(face, cq.Vector(0, 0, lowerSupportHeight))
            for face in self.baseBottomFaces
        ]
        footprint = cq.Workplane("XY").newObject(footprintSolids)

        if self.settings.compartmentsX > 1:
            for x in range(self.settings.compartmentsX - 1):
                xPos = (x + 1) * self.compartmentSizeX

                divider = (
                    resultPlane.box(
                        self.settings.dividerThickness,
                        self.internalSizeY,
                        dividerHeight,
                        centered=(True, False, False),
                        combine=False,
                    )
                    .translate((xPos, 0, 0))
                )
                result.add(divider)

                upperSupport = (
                    resultPlane.box(
                        self.settings.dividerThickness,
                        self.internalSizeY,
                        upperSupportHeight,
                        centered=(True, False, False),
                        combine=False,
                    )
                    .translate((xPos, 0, -upperSupportHeight))
                )
                result.add(upperSupport)

                lowerSupport = (
                    resultPlane.box(
                        self.settings.dividerThickness,
                        self.internalSizeY,
                        lowerSupportHeight,
                        centered=(True, False, False),
                        combine=False,
                    )
                    .translate((xPos, 0, -upperSupportHeight - lowerSupportHeight))
                )
                result.add(lowerSupport.intersect(footprint))

        if self.settings.compartmentsY > 1:
            for y in range(self.settings.compartmentsY - 1):
                yPos = (y + 1) * self.compartmentSizeY

                divider = (
                    resultPlane.box(
                        self.internalSizeX,
                        self.settings.dividerThickness,
                        dividerHeight,
                        centered=(False, True, False),
                        combine=False,
                    )
                    .translate((0, yPos, 0))
                )
                result.add(divider)

                upperSupport = (
                    resultPlane.box(
                        self.internalSizeX,
                        self.settings.dividerThickness,
                        upperSupportHeight,
                        centered=(False, True, False),
                        combine=False,
                    )
                    .translate((0, yPos, -upperSupportHeight))
                )
                result.add(upperSupport)

                lowerSupport = (
                    resultPlane.box(
                        self.internalSizeX,
                        self.settings.dividerThickness,
                        lowerSupportHeight,
                        centered=(False, True, False),
                        combine=False,
                    )
                    .translate((0, yPos, -upperSupportHeight - lowerSupportHeight))
                )
                result.add(lowerSupport.intersect(footprint))

        if self.settings.compartmentsX > 1 and self.settings.compartmentsY > 1:
            result = result.combine()

        return result

    def label_tab(self, basePlane):
        """Construct the pickup/label tab"""

        result = basePlane

        startX = self.grid.WALL_THICKNESS
        
        # Limit the height of the label ridge to avoid it being taller than the compartment
        labelRidgeHeight = min(self.compartmentSizeZ+2.25, self.settings.labelRidgeWidth-self.grid.CHAMFER_EPSILON)

        # Create the label tab profile and extrude it
        result.add(
            basePlane.sketch()
            .segment((startX,self.brickSizeZ-labelRidgeHeight),(startX,self.brickSizeZ))
            .segment((startX+self.settings.labelRidgeWidth,self.brickSizeZ))
            .close()
            .reset()
            .assemble()
            .finalize()
            .extrude(self.internalSizeX)
            .edges(">Y").fillet(0.5)
            )

        return result
        
    def validate_settings(self):
        """Do some sanity checking on the settings to prevent impossible or unreasonable results"""

        # Cap the size in grid-units to avoid thrashing the server
        self.settings.sizeUnitsX = min(self.settings.sizeUnitsX, self.grid.MAX_GRID_UNITS)
        self.settings.sizeUnitsY = min(self.settings.sizeUnitsY, self.grid.MAX_GRID_UNITS)
        self.settings.sizeUnitsZ = min(self.settings.sizeUnitsZ, self.grid.MAX_HEIGHT_UNITS)

        # Limit the number of compartment in each direction
        self.settings.compartmentsX = min(self.settings.compartmentsX, self.settings.sizeUnitsX*self.grid.MAX_COMPARTMENTS_PER_GRID_UNIT)
        self.settings.compartmentsY = min(self.settings.compartmentsY, self.settings.sizeUnitsY*self.grid.MAX_COMPARTMENTS_PER_GRID_UNIT)

        # Ensure the labeltab is smaller than half the compartmentsize, or it will close off a row
        self.settings.labelRidgeWidth = min(self.compartmentSizeY/2, self.settings.labelRidgeWidth)

    def generate_model(self):
        # Add the base of Gridfinity profiles
        result = self.grid_base(cq.Workplane("XY"))

        # Remember the base's own bottom-facing faces (the only spots that actually touch the
        # bin's true bottom at z=0 - the rest of the base is hollow, and adjacent units don't
        # touch each other there). Divider support plugs are clipped to these later so they
        # only ever fill in where solid material genuinely reaches the bottom.
        self.baseBottomFaces = result.faces("<Z").vals()

        # Continue from the top of the base
        plane = result.faces(">Z").workplane()

        # Remember how tall the base itself is (its top face height above the bin's true
        # bottom at z=0) so divider support plugs can be sized to reach all the way down to
        # solid material without any guesswork or duplicated magic numbers.
        self.baseTopZ = plane.plane.origin.z

        # Add the floor of the bin
        result.add(self.brick_floor(plane))

        # Add the outer walls
        plane = result.faces(">Z").workplane()
        result.add(self.outer_wall(plane))

        # Add the divider walls
        result.add(self.divider_walls(plane))

        # Add the grabbing/label tab
        if self.settings.addLabelRidge:
            plane = cq.Workplane("YZ").workplane(offset=self.grid.WALL_THICKNESS)
            result.add(self.label_tab(plane))      

        # Combine everything together
        result = result.combine()

        return result

    def generate_stl(self, filename):
        model = self.generate_model()
        exporters.export(model, filename)

