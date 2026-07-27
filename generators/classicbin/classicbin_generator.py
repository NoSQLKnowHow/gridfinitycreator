import cadquery as cq
from cadquery import exporters
from dataclasses import dataclass
from grid_constants import *
import logging

from generators.common.bin_base import bin_base
from generators.common.export import export_model
from generators.common import dimensions as dims
from generators.common import layout

logger = logging.getLogger('CBG')

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
        self.compartmentSizeZ = (self.settings.sizeUnitsZ-1)*self.grid.HEIGHT_UNITSIZE_MM

    def outer_wall(self, basePlane):
        """Create the outer wall of the bin"""

        sizeZ = self.compartmentSizeZ

        if self.settings.addStackingLip:
            sizeZ = sizeZ + self.grid.STACKING_LIP_HEIGHT

        wall = basePlane.box(self.brickSizeX, self.brickSizeY, sizeZ, centered=False, combine = False)
        
        thickness = self.grid.WALL_THICKNESS
        wall = wall.edges("|Z").fillet(self.grid.CORNER_FILLET_RADIUS)

        cutout = (
                    basePlane.center(thickness, thickness)
                    .box(self.internalSizeX, self.internalSizeY, sizeZ, centered=False, combine = False)
                )

        # If the walls are thicker than the outside radius of the corners, skip the fillet
        if thickness < self.grid.CORNER_FILLET_RADIUS:
            cutout = cutout.edges("|Z").fillet(self.grid.CORNER_FILLET_RADIUS-thickness)
        
        result = wall-cutout
        
        if self.settings.addStackingLip:
            result = result.edges(
                        cq.selectors.NearestToPointSelector((self.brickSizeX/2, self.brickSizeY/2, sizeZ*2))
                    ).chamfer(thickness-self.grid.CHAMFER_EPSILON)
            
        return result

    def parse_removed_walls(self):
        """Parse the removedWalls setting into a set of ('v'|'h', i, j) tuples"""
        return layout.parse_removed_walls(self.settings)

    def divider_walls(self, basePlane):
        """Create the internal divider walls. Walls are built per cell-edge
           segment so individual segments can be removed to merge cells into
           larger compartments (see the layout editor in the UI)."""

        removed = self.parse_removed_walls()

        resultPlane = basePlane.center(self.grid.WALL_THICKNESS, self.grid.WALL_THICKNESS)
        result = resultPlane.workplane()

        # Vertical walls (between columns), one segment per row
        for i in range(1, self.settings.compartmentsX):
            for j in range(self.settings.compartmentsY):
                if ('v', i, j) in removed:
                    continue
                result.add(
                    resultPlane.box(self.settings.dividerThickness, self.compartmentSizeY, self.compartmentSizeZ,
                        centered=(True, False, False), combine=False)
                    .translate((i*self.compartmentSizeX, j*self.compartmentSizeY, 0)))

        # Horizontal walls (between rows), one segment per column
        for j in range(1, self.settings.compartmentsY):
            for i in range(self.settings.compartmentsX):
                if ('h', i, j) in removed:
                    continue
                result.add(
                    resultPlane.box(self.compartmentSizeX, self.settings.dividerThickness, self.compartmentSizeZ,
                        centered=(False, True, False), combine=False)
                    .translate((i*self.compartmentSizeX, j*self.compartmentSizeY, 0)))

        return result

    def label_tab(self, basePlane):
        """Construct the pickup/label tab"""

        result = basePlane.workplane()

        removed = self.parse_removed_walls()
        numRidges = self.settings.compartmentsY if self.settings.multiLabel else 1
        labelRidgeHeight = min(self.compartmentSizeZ, self.settings.labelRidgeWidth-self.grid.CHAMFER_EPSILON)

        for x in range(numRidges):
            # Ridge x sits at the boundary between rows x-1 and x (x=0 leans on
            # the front outer wall). If the layout editor removed any wall
            # segment at that boundary, the rows are merged - skip the ridge so
            # the merged compartment only gets the one label at its front.
            if x > 0 and any(('h', i, x) in removed for i in range(self.settings.compartmentsX)):
                continue

            startX = self.grid.WALL_THICKNESS + x*self.compartmentSizeY
            result.add(
                basePlane.sketch()
                .segment((startX,self.brickSizeZ-labelRidgeHeight),(startX,self.brickSizeZ))
                .segment((startX+self.settings.labelRidgeWidth,self.brickSizeZ))
                .segment((startX+self.settings.labelRidgeWidth-labelRidgeHeight,self.brickSizeZ-labelRidgeHeight))
                .close()
                .reset()
                .assemble()
                .finalize()
                .extrude(self.internalSizeX)
                .edges(">Y").fillet(0.5)
                )
            
        return result

    def cells_with_scoop(self, removed):
        """Decide which cells get a grab-ramp, as {(i, y): bool}.

           A ramp spans its cell's full width and leans against the wall at the
           back of that cell. It is dropped when either:
             - its own backing wall was removed, so the ramp would float in
               mid-air inside the merged compartment, or
             - a side wall was removed AND the neighbour on that side has no
               ramp, which would leave this ramp's end face exposed into that
               90-degree opening.

           Cells merged only side-by-side keep their ramps (their backing walls
           are intact, so the ramps join into one continuous wide ramp), and so
           do cells merged front-to-back (the ramp still sits at the real back
           wall of the deeper compartment)."""

        cX = self.settings.compartmentsX
        cY = self.settings.compartmentsY

        hasScoop = {}
        for y in range(cY):
            for i in range(cX):
                backRemoved = (y + 1 < cY) and ('h', i, y + 1) in removed
                hasScoop[(i, y)] = not backRemoved

        # Dropping a ramp can expose its neighbour's end in turn, so keep
        # propagating until nothing changes
        changed = True
        while changed:
            changed = False
            for y in range(cY):
                for i in range(cX):
                    if not hasScoop[(i, y)]:
                        continue
                    openLeft = i >= 1 and ('v', i, y) in removed and not hasScoop[(i - 1, y)]
                    openRight = i + 1 < cX and ('v', i + 1, y) in removed and not hasScoop[(i + 1, y)]
                    if openLeft or openRight:
                        hasScoop[(i, y)] = False
                        changed = True

        return hasScoop

    def grab_curve(self, basePlane):

        result = basePlane.workplane()

        removed = self.parse_removed_walls()

        # To ensure the curve fits, take the smallest of: The height of the divider walls, the length of a compartment, half the brick unit-size (Y-direction)
        radius = min((self.settings.sizeUnitsZ-1) * self.grid.HEIGHT_UNITSIZE_MM, self.compartmentSizeY, self.grid.BRICK_UNIT_SIZE_Y/2)

        hasScoop = self.cells_with_scoop(removed)

        for y in range(self.settings.compartmentsY):
            # Ramps are built per cell, keeping merged compartments contiguous
            # (see cells_with_scoop for which cells qualify)
            boundary = y + 1
            startX = self.grid.WALL_THICKNESS + boundary*self.compartmentSizeY

            # One-cell-wide ramp solid for this row (at column 0), translated
            # into place for every cell that keeps its ramp
            rowRamp = (
                basePlane.sketch()
                .segment((startX,self.grid.HEIGHT_UNITSIZE_MM+radius),(startX,self.grid.HEIGHT_UNITSIZE_MM))
                .segment((startX-radius,self.grid.HEIGHT_UNITSIZE_MM))
                .arc((startX-radius,self.grid.HEIGHT_UNITSIZE_MM+radius),radius,270,90)
                .assemble()
                .finalize()
                .extrude(self.compartmentSizeX)
                )

            for i in range(self.settings.compartmentsX):
                if not hasScoop[(i, y)]:
                    continue
                result.add(rowRamp.translate((i*self.compartmentSizeX, 0, 0)))

        return result

    def validate_settings(self):
        """Do some sanity checking on the settings to prevent impossible or unreasonable results"""

        # Cap the size in grid-units to avoid thrashing the server
        self.settings.sizeUnitsX = min(self.settings.sizeUnitsX, self.grid.MAX_GRID_UNITS)
        self.settings.sizeUnitsY = min(self.settings.sizeUnitsY, self.grid.MAX_GRID_UNITS)
        self.settings.sizeUnitsZ = min(self.settings.sizeUnitsZ, self.grid.MAX_HEIGHT_UNITS)
        self.settings.sizeUnitsZ = max(self.settings.sizeUnitsZ, self.grid.MIN_HEIGHT_UNITS)

        # Limit the number of compartment in each direction
        self.settings.compartmentsX = min(self.settings.compartmentsX, self.settings.sizeUnitsX*self.grid.MAX_COMPARTMENTS_PER_GRID_UNIT)
        self.settings.compartmentsY = min(self.settings.compartmentsY, self.settings.sizeUnitsY*self.grid.MAX_COMPARTMENTS_PER_GRID_UNIT)

        # Ensure the labeltab is smaller than half the compartmentsize, or it will close off a row
        self.settings.labelRidgeWidth = min(self.compartmentSizeY/2, self.settings.labelRidgeWidth)

        # Ensure the label tab is not deeper than the interior height of the bin or it will stick out 
        # self.settings.labelRidgeWidth = min(self.compartmentSizeZ, self.settings.labelRidgeWidth)

    def generate_model(self):
        plane = cq.Workplane("XY")

        # First create the base
        result = bin_base(plane, self.settings, self.grid)

        # Continue at the top of the base
        plane = result.faces(">Z").workplane()

        # Add the outer walls
        result.add(self.outer_wall(plane))
        
        # Add the divider walls
        result.add(self.divider_walls(plane))

        # Continue from the left-most outside face of the brick
        plane = cq.Workplane("YZ").workplane(offset=self.grid.WALL_THICKNESS)

        # Add the grabbing/label tab
        if self.settings.addLabelRidge:
            result.add(self.label_tab(plane))

        # Add the curve
        if self.settings.addGrabCurve:
            result.add(self.grab_curve(plane))

        # Combine everything together
        result = result.combine(clean=True)

        return result

    def get_dimensions(self):
        """Real-world dimensions for the readout panel"""
        import math

        # Volume displaced by features protruding into the interior, using the
        # same cross-sections the geometry code builds

        # Label tab: trapezoid profile (see label_tab), one ridge per row when
        # multiLabel is set, extruded across the full internal width
        labelArea = 0
        labelVol = 0
        if self.settings.addLabelRidge:
            W = self.settings.labelRidgeWidth
            h = min(self.compartmentSizeZ, W - self.grid.CHAMFER_EPSILON)
            labelArea = h * (2 * W - h) / 2
            # Count the ridges actually built: label_tab skips boundaries whose
            # backing wall was removed by the layout editor
            removedWalls = self.parse_removed_walls()
            numRidges = 1
            if self.settings.multiLabel:
                numRidges += sum(
                    1 for x in range(1, self.settings.compartmentsY)
                    if not any(('h', i, x) in removedWalls for i in range(self.settings.compartmentsX)))
            labelVol = labelArea * self.internalSizeX * numRidges

        # Scoop ramp: square-minus-quarter-circle profile (see grab_curve),
        # built per cell - count only the segments actually present (a cell
        # whose backing wall was removed by the layout editor has no ramp)
        scoopArea = 0
        scoopVol = 0
        if self.settings.addGrabCurve:
            r = min((self.settings.sizeUnitsZ - 1) * self.grid.HEIGHT_UNITSIZE_MM,
                    self.compartmentSizeY, self.grid.BRICK_UNIT_SIZE_Y / 2)
            scoopArea = r * r * (1 - math.pi / 4)
            builtSegments = sum(1 for present in self.cells_with_scoop(self.parse_removed_walls()).values() if present)
            scoopVol = scoopArea * self.compartmentSizeX * builtSegments

        # Per-compartment: the scoop hits every compartment (one ramp per row);
        # the label tab hits every compartment only when there is a ridge on
        # every row, or just a single row
        cX = self.settings.compartmentsX
        usableX = (self.internalSizeX - self.settings.dividerThickness * (cX - 1)) / cX
        perCompArea = scoopArea
        if self.settings.multiLabel or self.settings.compartmentsY == 1:
            perCompArea += labelArea

        sections = [
            dims.bin_outer_section(self),
            dims.interior_section(self, self.compartmentSizeZ, labelVol + scoopVol),
            dims.compartment_section(self, self.compartmentSizeZ, perCompArea * usableX),
        ]
        return [s for s in sections if s]

    def generate_stl(self, filename):
        model = self.generate_model()
        logger.debug("Saved classicbin to {0}".format(filename))
        export_model(model, filename)


