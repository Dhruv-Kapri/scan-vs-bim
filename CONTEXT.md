# Scan vs BIM

Checking a laser scan of a building against its BIM model, element by element, and saying what the
scan shows was built, shifted or not there.

## Inputs

**Scan**:
A point cloud of the real building from a terrestrial laser scanner, possibly merged from several
scanner positions.
_Avoid_: point cloud (when the scan specifically is meant), capture

**Model**:
The BIM description of the building as an IFC file (or, for PC2Model, an OBJ mesh).
_Avoid_: BIM (as a noun for the file), design

**Element**:
One fixed building part in the model (wall, slab, column, door, window, covering, stair), the unit a
verdict is given for. Furniture is not an element.
_Avoid_: object, component, entity

**Clutter**:
Scan points that belong to no element: furniture, equipment, people, cables.
_Avoid_: noise (that is measurement error), furniture (too narrow)

**Scan class**:
A semantic label attached to scan points by the dataset (CRAS: wall, floor, desk, cable…). Not the
same as an element's IFC class.
_Avoid_: category (PC2Model uses that for sample groups)

**Scanner position**:
Where the scanner stood for one of the scans that were merged; needed to tell what it could see.
_Avoid_: station, viewpoint

**Oracle labels**:
Scan classes used as if they were a perfect segmentation, to separate clutter from elements; an
upper bound, not something a new scan would have.

**Perturbed model**:
A copy of the model with deliberately injected, recorded deviations (elements moved by known
offsets, or deleted: a deleted element stays in the IFC and the scan points on it are masked out,
see **Deleted element**), used as known answers for verdicts.
_Avoid_: synthetic model, fake model

**Deleted element**:
In a perturbed model, an element declared not to exist: it stays in the IFC, and the scan points
on it are masked out of the comparison, as if it had not been built. The perturbed-model word; "not built" is kept for what a Missing verdict is evidence of.
_Avoid_: not built (for the injected change), removed

**Geometric mask**:
The mask of a deleted element: the element-class scan points within BAND of its surface, whoever
the baseline assigned them to. It also removes the points of neighbours that lie within BAND of it.
_Avoid_: mask by assignment (the first version of 03b, which leaks)

**Leak**:
Element-class scan points that still land on a deleted element in the perturbed run, because they
belonged to a neighbour in the baseline and the neighbour has moved. A mask by assignment leaks; a
geometric mask does not, in a frozen frame.

**Frozen frame**:
The perturbed run scored with the real model's refined registration, so that the only differences
from the baseline are the injected changes (the known-answer test is about the comparison, not the
registration).

**Dragged frame**:
The registration refined against the perturbed model, which is what a real pipeline would get when
the model is wrong. In 03b it differs from the frozen frame by the ICP pull.

**ICP pull**:
The shift of the refined registration caused by injected moves of walls: ICP fits the moved walls
and moves the whole scan with them (13.2 mm along y in 03b). Not an error in the scan.

**Stress model**:
A perturbed model with several moves and deletions at once (03b: three walls moved 1, 3 and 10 cm,
plus the three deletions), used for what only appears when changes coexist: the leak and the ICP
pull. The known-answer runs are separate perturbed models, one change each.

**Pure shift**:
What the unchanged verdict logic gives on a wall's own baseline offsets shifted by an injected
change, with no perturbed model involved. A move is a **fair verdict test** for a variant only if
its pure shift gives the expected verdict; the run can then differ from it only through what the
move does to which points enter the band.

## Alignment

**Registration**:
Placing the scan in the model's coordinate frame by a rigid transform (plus scale where needed).
_Avoid_: alignment (fine in prose, but the metrics say registration), fitting

**Registration residual**:
Distance between the registered scan points and the model surface (PC2Model calls its mean
`LOA_mean`). A measure of registration quality, not an accuracy level.
_Avoid_: LOA

## Comparison

**Accuracy level**:
A USIBD Level of Accuracy band (LOA10–LOA50), stated at 95% confidence (about 2σ). The project's
tolerance is the LOA30 band.
_Avoid_: LOA (on its own, ambiguous with PC2Model's metric), precision

**Tolerance**:
The largest deviation at which an element still counts as built as modelled; taken from the
accuracy level, never invented.

**Room-facing face**:
A wall face whose outward normal points into the room. A wall on the room's boundary has one
room-facing side, a partition standing inside it has two.

**Wall side test**:
Deciding, per scan point on a wall, which side of the wall it was seen from, using free space in
the scan itself (no scanner positions are needed). A point seen from a room-facing side counts for
that side's face; a point seen from the other side is the back of the wall. Where the scan cannot
tell, see ambiguous side.
_Avoid_: normal test (unoriented point normals cannot tell the two faces of a thin wall apart)

**Back of the wall**:
Scan points on a wall's far face, seen from the neighbouring room. They are left out of the wall's
verdict. A wall moved out of the room by its own thickness would put its scan surface in the same
place; only the scan around it can tell them apart.

**Ambiguous side**:
A scan point whose side of the wall the scan cannot tell (free or occupied on both sides, or the
other face not scanned behind it). It is measured to the nearest room-facing face, and the share of
such points is reported per wall. A wall that is mostly ambiguous keeps the nearest-face reading,
including its folding.

**Reference side**:
For a wall with two room-facing sides, the side (outward normal) with more scan points. All of the
wall's offsets are expressed along it, so a moved partition reads one offset, not +d and -d. For a
wall with one room-facing side the offset is positive towards the room, as for every other
element; for a two-sided wall it is positive along the reference side's normal.

**Junction margin**:
A wall's scan points within a set distance (10 cm in 03a) of any other element's surface (ceiling,
floor, window, door, another wall) are left out of that wall's verdict: at a junction a point could
belong to either element. The verdict of a wall is then about its plain area.

**Verdict**:
The outcome for one element: OK, shifted, missing, not visible, or not confirmed.
_Avoid_: status, result, label

**OK**:
Enough scan points lie within tolerance of the element's surface.

**Shifted**:
The element's scan points cluster at a consistent offset beyond tolerance.
_Avoid_: moved, deviated

**Missing**:
A scanner position had line of sight to the element's surface, yet the scan has too few points on
it: evidence that it was not built.
_Avoid_: absent, not built

**Not visible**:
No scanner position had line of sight to the element's surface (occluded), so the scan says nothing
about it. Not scanned is not the same as not built.
_Avoid_: occluded (fine in prose), hidden

**Not confirmed**:
The scan cannot settle the element: too few scan points on it and no scanner positions to say why
(missing and not visible cannot be told apart), or enough points that neither lie within tolerance
nor cluster at one offset (clutter mixed in, or only a sliver of the element in view).
_Avoid_: unknown, missing (when visibility was not checked)
