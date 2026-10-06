import cadquery as cq
from cadquery import exporters
from grid_constants import *
from generators.common import dimensions as dims
from generators.common.export import export_model

# Geometry constants for the slab features (mm)
SKELETON_CUTOUT_DIAMETER = 27    # Per-cell through-cutout; clears magnet holes at the cell corners
WEIGHT_POCKET_SIZE = 20          # Square top-opening pocket per cell; clears magnet holes
WEIGHT_POCKET_FLOOR = 1.0        # Material left below a weight pocket
WEIGHT_POCKET_FLOOR_SCREWS = 2.4 # Thicker pocket floor when a screw countersink is recessed into it
SCREW_HOLE_DIAMETER = 3.5        # M3 clearance
SCREW_CSK_DIAMETER = 7.5         # Countersink for an M3 flat head
MIN_MAGNET_FLOOR = 0.4           # Material left below a magnet hole

class Generator:
    def __init__(self, settings, grid) -> None:
        self.settings = settings
        self.grid = grid

        self.validate_settings()

    def base_grid(self):
        """Create the grid frame the bins click into"""
        x_offs = -self.grid.GRID_UNIT_SIZE_X_MM/2
        frame_pts = [(0+x_offs,0), (0+x_offs,4.65), (2.25+x_offs, 2.5), (2.25+x_offs, 0.7), (2.85+x_offs,0)]

        path = cq.Workplane("XY").rect(self.grid.GRID_UNIT_SIZE_X_MM, self.grid.GRID_UNIT_SIZE_Y_MM).val()
        path = path.fillet2D(4, path.Vertices())

        corners = (
            cq.Workplane("XY")
            .box(self.grid.GRID_UNIT_SIZE_X_MM,self.grid.GRID_UNIT_SIZE_Y_MM,4.65)
            .translate((0,0,4.65/2))
            .faces(">Z")
            .sketch()
            .rect(42, 42)
            .vertices()
            .fillet(4)
            .finalize()
            .cutThruAll()
        )

        unit = corners + (
            cq.Workplane("XZ")
            .polyline(frame_pts)
            .close()
            .sweep(path)
            )

        result = cq.Workplane("XY")

        for x in range(self.settings.sizeUnitsX):
            for y in range(self.settings.sizeUnitsY):
                result.add(unit.translate((x*self.grid.GRID_UNIT_SIZE_X_MM, y*self.grid.GRID_UNIT_SIZE_Y_MM, 0)))

        result = result.combine(clean=True)
        result = result.edges("|Z").fillet(3.999)

        return result

    def cell_centers(self):
        """World XY center of every grid cell"""
        return [
            (x * self.grid.GRID_UNIT_SIZE_X_MM, y * self.grid.GRID_UNIT_SIZE_Y_MM)
            for x in range(self.settings.sizeUnitsX)
            for y in range(self.settings.sizeUnitsY)
        ]

    def base_slab(self):
        """Create the solid slab below the frame, with the requested features cut in.
           The slab spans z = -baseThickness .. 0; the frame sits on top of it."""

        t = self.settings.baseThickness
        sizeX = self.settings.sizeUnitsX * self.grid.GRID_UNIT_SIZE_X_MM
        sizeY = self.settings.sizeUnitsY * self.grid.GRID_UNIT_SIZE_Y_MM

        # Center the slab on the frame's footprint (unit centers start at the origin)
        slab = (
            cq.Workplane("XY")
            .box(sizeX, sizeY, t)
            .translate((
                sizeX/2 - self.grid.GRID_UNIT_SIZE_X_MM/2,
                sizeY/2 - self.grid.GRID_UNIT_SIZE_Y_MM/2,
                -t/2,
            ))
        )
        # Match the frame's outer corner rounding
        slab = slab.edges("|Z").fillet(3.999)

        if self.settings.baseStyle == "skeleton":
            # A large round through-cutout per cell keeps the click-in rim and the
            # magnet corners while dropping most of the plastic and print time
            for cx, cy in self.cell_centers():
                slab = slab - (
                    cq.Workplane("XY")
                    .cylinder(t + 2, SKELETON_CUTOUT_DIAMETER / 2)
                    .translate((cx, cy, -t/2))
                )

        if self.settings.baseStyle == "weighted":
            # Square pockets opening from the TOP of the slab (inside each cell, below
            # where the bins sit): drop in steel plate/washers/BBs and the bins cover
            # them. Opening upward keeps the underside completely flat, so the plate
            # prints without any supports.
            floorSkin = WEIGHT_POCKET_FLOOR_SCREWS if self.settings.addScrewHoles else WEIGHT_POCKET_FLOOR
            pocketDepth = t - floorSkin
            for cx, cy in self.cell_centers():
                pocket = (
                    cq.Workplane("XY")
                    .box(WEIGHT_POCKET_SIZE, WEIGHT_POCKET_SIZE, pocketDepth)
                    .edges("|Z")
                    .fillet(2)
                    .translate((cx, cy, -pocketDepth/2))
                )
                slab = slab - pocket

        if self.settings.addMagnetHoles:
            # Same in-cell positions as the bins use (shared grid constants), so
            # bin and plate magnets line up. Inserted from the top of the slab.
            depth = self.grid.DEFAULT_MAGNET_HOLE_DEPTH
            radius = self.settings.magnetHoleDiameter / 2
            for cx, cy in self.cell_centers():
                for ox in (-self.grid.HOLE_OFFSET_X, self.grid.HOLE_OFFSET_X):
                    for oy in (-self.grid.HOLE_OFFSET_Y, self.grid.HOLE_OFFSET_Y):
                        slab = slab - (
                            cq.Workplane("XY")
                            .cylinder(depth, radius)
                            .translate((cx + ox, cy + oy, -depth/2))
                        )

        if self.settings.addScrewHoles:
            # Countersunk mounting hole through the center of each cell. The head
            # sits below the frame profile, so bins are unaffected. On a weighted
            # plate the countersink is recessed into the (thickened) pocket floor.
            cskDepth = (SCREW_CSK_DIAMETER - SCREW_HOLE_DIAMETER) / 2  # ~90 degree countersink
            if self.settings.baseStyle == "weighted":
                cskTopZ = -(t - WEIGHT_POCKET_FLOOR_SCREWS)  # top of the pocket floor
            else:
                cskTopZ = 0  # top of the slab
            for cx, cy in self.cell_centers():
                through = (
                    cq.Workplane("XY")
                    .cylinder(t + 2, SCREW_HOLE_DIAMETER / 2)
                    .translate((cx, cy, -t/2))
                )
                csk = cq.Solid.makeCone(
                    SCREW_HOLE_DIAMETER / 2,
                    SCREW_CSK_DIAMETER / 2,
                    cskDepth,
                    cq.Vector(cx, cy, cskTopZ - cskDepth),
                )
                slab = slab - through - cq.Workplane("XY").newObject([csk])

        return slab

    def validate_settings(self):
        """Do some sanity checking on the settings to prevent impossible or unreasonable results"""

        # Cap the size in grid-units to avoid thrashing the server
        self.settings.sizeUnitsX = min(self.settings.sizeUnitsX, self.grid.MAX_GRID_UNITS)
        self.settings.sizeUnitsY = min(self.settings.sizeUnitsY, self.grid.MAX_GRID_UNITS)

        if self.settings.baseStyle not in ("standard", "solid", "skeleton", "weighted"):
            self.settings.baseStyle = "standard"

        # Magnet or screw holes need material to sit in - upgrade a frame-only
        # plate to a solid one rather than silently ignoring the request
        if self.settings.baseStyle == "standard" and (self.settings.addMagnetHoles or self.settings.addScrewHoles):
            self.settings.baseStyle = "solid"

        # Screw holes sit at the cell centers, which the skeleton cutout removes
        # entirely - they only work where there is material there (solid/weighted)
        if self.settings.baseStyle == "skeleton":
            self.settings.addScrewHoles = False

        # Keep the slab printable and thick enough for the features cut into it
        self.settings.baseThickness = min(max(self.settings.baseThickness, 1.0), 10.0)
        if self.settings.addMagnetHoles:
            self.settings.baseThickness = max(
                self.settings.baseThickness,
                self.grid.DEFAULT_MAGNET_HOLE_DEPTH + MIN_MAGNET_FLOOR,
            )
        if self.settings.baseStyle == "weighted":
            # Room for a useful pocket (>= 2mm) above the pocket floor
            floorSkin = WEIGHT_POCKET_FLOOR_SCREWS if self.settings.addScrewHoles else WEIGHT_POCKET_FLOOR
            self.settings.baseThickness = max(self.settings.baseThickness, floorSkin + 2.0)

        self.settings.magnetHoleDiameter = min(max(self.settings.magnetHoleDiameter, 1.0), 10.0)

    def generate_model(self):
        plane = cq.Workplane("XY")
        result = plane.workplane()

        # Add the base of Gridfinity profiles
        result.add(self.base_grid())

        # Add the slab below it, if any style needing one is selected
        if self.settings.baseStyle != "standard":
            result.add(self.base_slab())

        # Combine everything together
        result = result.combine(clean=True)

        return result

    def get_dimensions(self):
        """Real-world dimensions for the readout panel"""
        sizeX = self.settings.sizeUnitsX * self.grid.GRID_UNIT_SIZE_X_MM
        sizeY = self.settings.sizeUnitsY * self.grid.GRID_UNIT_SIZE_Y_MM
        height = 4.65  # frame profile height
        if self.settings.baseStyle != "standard":
            height += self.settings.baseThickness

        rows = [
            ["Footprint", dims.mm2(sizeX, sizeY)],
            ["Total height", dims.mm(height)],
            ["Cells", f"{self.settings.sizeUnitsX} × {self.settings.sizeUnitsY}"],
        ]

        if self.settings.baseStyle == "weighted":
            floorSkin = WEIGHT_POCKET_FLOOR_SCREWS if self.settings.addScrewHoles else WEIGHT_POCKET_FLOOR
            pocketDepth = self.settings.baseThickness - floorSkin
            rows.append(["Weight pockets", dims.mm3(WEIGHT_POCKET_SIZE, WEIGHT_POCKET_SIZE, pocketDepth) + " each"])

        return [{"title": "Baseplate", "rows": rows}]

    def generate_stl(self, filename):
        model = self.generate_model()
        export_model(model, filename)
