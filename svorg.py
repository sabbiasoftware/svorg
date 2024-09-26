#!/usr/bin/python3
import os
import argparse
import json
from json import JSONDecodeError
from io import StringIO

class Node:
    def __init__(self, attrs) -> None:
        # default values
        self.ParentId = None
        self.LevelOffset = 0
        self.StackChildren = None
        self.NodeTemplate="NodeTemplate"
        self.LineTemplate="LineTemplate"
        self.StackLineTemplate="StackLineTemplate"

        # later calculated attributes
        self.Width = 0
        self.Height = 0
        self.x = 0
        self.y = 0

        for key, value in attrs.items():
            setattr(self, key, value)

# Set level and width of node and its children recursively
def prepare(cfg, t, node, stackChildren):
    if node.StackChildren is None:
        node.StackChildren = stackChildren

    children = list(m for m in t if m.ParentId == node.Id)
    if len(children) == 0:
        node.Width = cfg["NodeWidth"] + 2 * cfg["Pad"]
        node.Height = cfg["NodeHeight"] + cfg["Pad"]
    else:
        if node.StackChildren:
            node.Height = cfg["NodeHeight"] + cfg["LevelPad"]
            for child in children:
                prepare(cfg, t, child, node.StackChildren)
                node.Height += child.Height
            node.Width = max(child.Width for child in children) + 4 * cfg["StackPad"]
        else:
            node.Width = 0
            for child in children:
                prepare(cfg, t, child, node.StackChildren)
                node.Width += child.Width
            node.Height = max(child.Height for child in children)

# Set width and height of ALL nodes recursively, starting with the root node(s)
def prepareAll(cfg, t):
    for n in (m for m in t if m.ParentId is None):
        prepare(cfg, t, n, False)

# Write SVG header
def writeHeader(f, cfg, totalWidth, totalHeight):
    params = {}
    params.update(cfg)
    params["TotalWidth"] = totalWidth
    params["TotalHeight"] = totalHeight

    f.write(cfg["SvgTemplate"].format(**params))

# Create calculated node fields that can be referred from templates
def createNodeCoordinates(cfg, node, params, prefix):
    params[prefix + "Left"] = node.x + node.Width // 2 - cfg["NodeWidth"] // 2
    params[prefix + "LeftPlusStackPad"] = node.x + node.Width // 2 - cfg["NodeWidth"] // 2 + cfg["StackPad"]
    params[prefix + "Right"] = node.x + node.Width // 2 + cfg["NodeWidth"] // 2
    params[prefix + "RightMinusStackPad"] = node.x + node.Width // 2 - cfg["NodeWidth"] // 2 - cfg["StackPad"]
    params[prefix + "Center"] = node.x + node.Width // 2
    params[prefix + "Top"] = node.y
    params[prefix + "Bottom"] = node.y + cfg["NodeHeight"]
    params[prefix + "Middle"] = node.y + cfg["NodeHeight"] // 2

# Create all node fields that can be referred from templates, which is the union of:
# - all key-value pairs in cfg
# - all attributes of node
# - calculated coordinate fields of node
# - if parent exists, calculated coordinate fields of parent
def createNodeParams(cfg, t, node):
    params = {}
    params.update(cfg)
    params.update(vars(node))

    createNodeCoordinates(cfg, node, params, "")
    if node.ParentId is not None:
        createNodeCoordinates(cfg, list(n for n in t if n.Id == node.ParentId)[0], params, "Parent")
    
    return params

# Write the node representation to SVG by applying the node parameters on the node template
def writeRect(f, cfg, t, node):
    params = createNodeParams(cfg, t, node)
    f.write(cfg[node.NodeTemplate].format(**params))

# Write the line representation to SVG by applying the node parameters on the node template
def writeLine(f, cfg, t, node):
    if node.ParentId is not None:
        params = createNodeParams(cfg, t, node)
        if list(n for n in t if n.Id == node.ParentId)[0].StackChildren:
            f.write(cfg[node.StackLineTemplate].format(**params))
        else:
            f.write(cfg[node.LineTemplate].format(**params))

# Write all nodes to SVG
def writeNodes(f, cfg, t):
    parentIds = [None]
    while len(parentIds) > 0:
        parentIdsNew = []
        for parentId in parentIds:
            parent = None if parentId is None else list(m for m in t if m.Id == parentId)[0]
            x = 0 if parent is None else parent.x
            y = cfg["Pad"] if parent is None else parent.y + cfg["NodeHeight"] + cfg["LevelPad"]# + (1 + parent.LevelOffset) * (cfg["NodeHeight"] + cfg["LevelPad"])

            for child in (m for m in t if m.ParentId == parentId):
                if parent is None or parent.StackChildren:
                    child.x = x + 4 * cfg["StackPad"]
                    child.y = y + child.LevelOffset * (cfg["NodeHeight"] + cfg["LevelPad"])
                    y += child.Height
                else:
                    child.x = x
                    child.y = y + child.LevelOffset * (cfg["NodeHeight"] + cfg["LevelPad"])
                    x += child.Width
                parentIdsNew.append(child.Id)
        parentIds = parentIdsNew

    for n in t:
        writeLine(f, cfg, t, n)

    for n in t:
        writeRect(f, cfg, t, n)

# Write SVG footer
def writeFooter(f):
    f.write('</svg>')

# Write entire SVG to stream
def writeAll(f, cfg, t):
    ff = StringIO()
    writeNodes(ff, cfg, t)
    totalWidth = max(n.x + n.Width for n in t) + 2 * cfg["Pad"]
    totalHeight = max(n.y + n.Height for n in t) + 2 * cfg["Pad"]
    writeHeader(f, cfg, totalWidth, totalHeight)
    f.write(ff.getvalue())
    writeFooter(f)

# Open and parse config and input JSON
def parseJson(fn):
    if not os.path.exists(fn):
        print("File does not exist: '{}'".format(fn))
        exit(1)

    parsedJson = None
    try:
        with open(fn, "r", encoding="utf-8") as f:
            parsedJson = json.load(f)
    except JSONDecodeError as e:
        print("Could not parse '{}' in line {} at column {}, message: '{}'".format(fn, e.lineno, e.colno, e.msg))
        exit(1)
    except Exception as e:
        print("Could not parse '{}'\n{}".format(fn, e))
        exit(1)
    return parsedJson



parser = argparse.ArgumentParser("svorg - A simplistic SVG org chart generator.")
parser.add_argument("-c", "--config", help="config file to use (regarding format check README and/or sample.cfg)", default="sample.cfg")
parser.add_argument("-i", "--input", help="data file to use (regarding format check README and/or sample.json)", required=True)
parser.add_argument("-o", "--overwrite", help="overwrite output without asking", action="store_true")
parser.add_argument("output", help="output SVG to generate")
args = parser.parse_args()

cfg = parseJson(args.config)
dat = parseJson(args.input)

t = []
for d in dat:
    t.append(Node(d))

prepareAll(cfg, t)

if not args.overwrite and os.path.exists(args.output):
    if input("Overwrite '{}'? [y/N] ".format(args.output)).lower() != 'y':
        exit(0)

with open(args.output, "w", encoding="utf-8") as f:
    writeAll(f, cfg, t)
