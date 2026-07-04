"""Small helper library for hand-laying-out draw.io (.drawio) files with
precise coordinates -- used where Graphviz's automatic rank layout can't
reliably give tight, centered, readable results (see docs/diagrams/readme.md).
"""
import base64
import os
import xml.etree.ElementTree as ET

import diagrams

REPO = "/Users/jyje/repo/jyje/cluster"
ICONS = os.path.join(REPO, "docs/assets/icons")
RES = os.path.join(os.path.dirname(os.path.dirname(diagrams.__file__)), "resources")


def data_uri(path):
    # NOTE: mxGraph style strings split on ";", so a standard data URI
    # ("data:image/png;base64,...") corrupts the style. Drop the ";base64"
    # marker -- this is the exact form draw.io itself emits when you embed
    # an image via the GUI, and mxGraph's image loader still treats the
    # payload as base64.
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/png,{b64}"


def vendored(name):
    return data_uri(os.path.join(ICONS, name))


def bundled(rel):
    return data_uri(os.path.join(RES, rel))


class DrawioDoc:
    def __init__(self, name, page_w, page_h, bg="#F7F8FA"):
        self.page_w, self.page_h = page_w, page_h
        self._id = 1
        self.mxfile = ET.Element("mxfile", host="app.diagrams.net")
        diagram = ET.SubElement(self.mxfile, "diagram", name=name, id="d1")
        model = ET.SubElement(
            diagram, "mxGraphModel",
            dx="1600", dy="900", grid="0", gridSize="10", guides="1", tooltips="1",
            connect="1", arrows="1", fold="1", page="1", pageScale="1",
            pageWidth=str(page_w), pageHeight=str(page_h), math="0", shadow="0",
        )
        self.root = ET.SubElement(model, "root")
        ET.SubElement(self.root, "mxCell", id="0")
        ET.SubElement(self.root, "mxCell", id="1", parent="0")
        if bg:
            self.add_rect(0, 0, page_w, page_h, f"fillColor={bg};strokeColor=none;")

    def next_id(self):
        self._id += 1
        return f"n{self._id}"

    def add_rect(self, x, y, w, h, style, value=""):
        cid = self.next_id()
        cell = ET.SubElement(self.root, "mxCell", id=cid, value=value, style=style,
                              vertex="1", parent="1")
        ET.SubElement(cell, "mxGeometry", x=str(x), y=str(y), width=str(w), height=str(h),
                      **{"as": "geometry"})
        return cid

    def add_text(self, x, y, w, h, text, size=20, color="#1F2937", bold=True,
                 align="left", valign="middle"):
        style = (f"text;html=1;fontSize={size};fontStyle={1 if bold else 0};"
                 f"fontColor={color};align={align};verticalAlign={valign};")
        return self.add_rect(x, y, w, h, style, text)

    def add_icon(self, x, y, uri, label, size=60, fontsize=11):
        style = (
            "shape=image;html=1;imageAspect=1;verticalLabelPosition=bottom;"
            "verticalAlign=top;labelBackgroundColor=none;"
            f"fontSize={fontsize};fontStyle=1;fontColor=#1F2937;"
            f"image={uri};"
        )
        return self.add_rect(x, y, size, size, style, label)

    def add_edge(self, src, dst, color="#334155", dashed=False, dotted=False, label="",
                 exit_side=None, entry_side=None, waypoints=None):
        """exit_side/entry_side: "top"/"bottom"/"left"/"right", to force the
        edge out of a specific face of src/dst instead of whatever side the
        default orthogonal router picks. waypoints: [(x, y), ...] absolute
        canvas coordinates the edge is forced through -- needed whenever a
        straight exit/entry pairing would still cut through an unrelated box
        in between (e.g. dropping through a crowded row on its way to the
        gap between tiers)."""
        sides = {"top": (0.5, 0), "bottom": (0.5, 1), "left": (0, 0.5), "right": (1, 0.5)}
        # NOTE: edgeStyle=orthogonalEdgeStyle is a *computed* router that
        # ignores an explicit points array entirely. When we're supplying
        # waypoints ourselves (to steer clear of a box in between), leave
        # edgeStyle unset -- draw.io then draws straight segments between
        # consecutive points, which reads identically to orthogonal routing
        # as long as consecutive points share an x or y (as ours do).
        edge_style = "" if waypoints else "edgeStyle=orthogonalEdgeStyle;"
        style = (f"{edge_style}rounded=1;html=1;strokeColor={color};"
                  "strokeWidth=2;endArrow=block;endFill=1;fontSize=11;fontColor=#334155;")
        if exit_side:
            x, y = sides[exit_side]
            style += f"exitX={x};exitY={y};exitDx=0;exitDy=0;"
        if entry_side:
            x, y = sides[entry_side]
            style += f"entryX={x};entryY={y};entryDx=0;entryDy=0;"
        if dotted:
            style += "dashed=1;dashPattern=1 3;endArrow=open;"
        elif dashed:
            style += "dashed=1;"
        cid = self.next_id()
        cell = ET.SubElement(self.root, "mxCell", id=cid, value=label, style=style,
                              edge="1", parent="1", source=src, target=dst)
        geo = ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})
        if waypoints:
            arr = ET.SubElement(geo, "Array", **{"as": "points"})
            for x, y in waypoints:
                ET.SubElement(arr, "mxPoint", x=str(x), y=str(y))
        return cid

    def box(self, x, y, w, h, key, color, title):
        """A titled group box. Returns nothing; caller places content with
        icon_row(), using the same (x, w) so rows can be centered in it."""
        self.add_rect(x, y, w, h, f"rounded=1;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor={color};strokeWidth=2;")
        self.add_text(x + 14, y + 8, w - 24, 26, title, size=15, color=color)

    def add_monogram(self, x, y, monogram, caption, color, size=56, fontsize=10):
        """Fallback for components with no usable official icon-only logo
        (e.g. Tempo, Sealed Secrets): a colored initials chip + caption."""
        self.add_rect(x, y, size, size,
                      f"ellipse;whiteSpace=wrap;html=1;fillColor={color};strokeColor=none;"
                      f"fontColor=#FFFFFF;fontSize={round(size / 2.2)};fontStyle=1;",
                      monogram)
        return self.add_text(x - 20, y + size + 4, size + 40, 18, caption,
                              size=fontsize, color="#1F2937", align="center")

    def icon_row(self, box_x, box_w, y, items, gap=18):
        """One row of icons, centered as a group within [box_x, box_x+box_w].
        Each item is either ("icon", uri, label, size, fontsize) or
        ("mono", monogram, caption, color, size, fontsize)."""
        sizes = [item[-2] for item in items]
        total = sum(sizes) + gap * (len(items) - 1)
        x = box_x + (box_w - total) / 2
        ids = []
        for item in items:
            kind = item[0]
            if kind == "icon":
                _, uri, label, size, fontsize = item
                ids.append(self.add_icon(x, y, uri, label, size=size, fontsize=fontsize))
            else:
                _, mono, caption, color, size, fontsize = item
                ids.append(self.add_monogram(x, y, mono, caption, color, size=size, fontsize=fontsize))
            x += size + gap
        return ids

    def write(self, path):
        tree = ET.ElementTree(self.mxfile)
        ET.indent(tree, space="  ")
        tree.write(path, encoding="utf-8", xml_declaration=True)
        print("wrote", path)
