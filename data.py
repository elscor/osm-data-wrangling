import csv
import codecs
import pprint
import re
import xml.etree.cElementTree as ET

import cerberus
import audit
import schema

OSM_PATH = "data/beijing_china.osm"

NODES_PATH = "data/nodes.csv"
NODE_TAGS_PATH = "data/nodes_tags.csv"
WAYS_PATH = "data/ways.csv"
WAY_NODES_PATH = "data/ways_nodes.csv"
WAY_TAGS_PATH = "data/ways_tags.csv"

LOWER_COLON = re.compile(r'^([a-z]|_)+:([a-z]|_)+')
PROBLEMCHARS = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')

SCHEMA = schema.schema
NODE_FIELDS = schema.NODE_FIELDS
NODE_TAGS_FIELDS = schema.NODE_TAGS_FIELDS
WAY_FIELDS = schema.WAY_FIELDS
WAY_TAGS_FIELDS = schema.WAY_TAGS_FIELDS
WAY_NODES_FIELDS = schema.WAY_NODES_FIELDS

def shape_element(element, node_attr_fields=NODE_FIELDS, way_attr_fields=WAY_FIELDS,
                  problem_chars=PROBLEMCHARS, default_tag_type='regular'):
    """Clean and shape node or way XML element to Python dict"""

    node_attribs = {}
    way_attribs = {}
    way_nodes = []
    tags = []  # Handle secondary tags the same way for both node and way elements

    for tag_elem in element.iter('tag'):
        tag = {}
        tag['id'] = element.attrib['id']
        if PROBLEMCHARS.match(tag_elem.attrib['k']):
            continue
        elif LOWER_COLON.match(tag_elem.attrib['k']):
            ind = tag_elem.attrib['k'].find(':')
            tag['key'] = tag_elem.attrib['k'][ind+1:]
            tag['type'] = tag_elem.attrib['k'][0:ind]
            if tag_elem.attrib['k'] == "name:en":
                tag['value'] = audit.update_way_names(tag_elem.attrib['v'], audit.mapping)
            elif tag_elem.attrib['k'] == "addr:postcode":
                if audit.check_postcode(tag_elem.attrib['v']):
                    tag['value'] = tag_elem.attrib['v']
                else:
                    continue
            else:
                tag['value'] = tag_elem.attrib['v']
        else:
            tag['key'] = tag_elem.attrib['k']
            tag['value'] = tag_elem.attrib['v']
            tag['type'] = default_tag_type
        tags.append(tag)

    if element.tag == 'node':
        for attr in node_attr_fields:
            node_attribs[attr] = element.attrib[attr]

        return {'node': node_attribs, 'node_tags': tags}

    elif element.tag == 'way':
        for attr in way_attr_fields:
            way_attribs[attr] = element.attrib[attr]

        i = 0
        for nd_elem in element.iter('nd'):
            way_node = {}
            way_node['id'] = element.attrib['id']
            way_node['node_id'] = nd_elem.attrib['ref']
            way_node['position'] = i
            i = i + 1
            way_nodes.append(way_node)

        return {'way': way_attribs, 'way_nodes': way_nodes, 'way_tags': tags}


# ================================================== #
#               Helper Functions                     #
# ================================================== #
def get_element(osm_file, tags=('node', 'way', 'relation')):
    """Yield element if it is the right type of tag"""

    context = ET.iterparse(osm_file, events=('start', 'end'))
    _, root = next(context)
    for event, elem in context:
        if event == 'end' and elem.tag in tags:
            yield elem
            root.clear()


def validate_element(element, validator, schema=SCHEMA):
    """Raise ValidationError if element does not match schema"""
    if validator.validate(element, schema) is not True:
        field, errors = next(validator.errors.iteritems())
        message_string = "\nElement of type '{0}' has the following errors:\n{1}"
        error_string = pprint.pformat(errors)

        raise Exception(message_string.format(field, error_string))


class UnicodeDictWriter(csv.DictWriter, object):
    """Extend csv.DictWriter to handle Unicode input"""

    def writerow(self, row):
        super(UnicodeDictWriter, self).writerow({
            k: (v.encode('utf-8') if isinstance(v, unicode) else v) for k, v in row.iteritems()
        })

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


# ================================================== #
#               Main Function                        #
# ================================================== #
def process_map(file_in, validate):
    """Iteratively process each XML element and write to csv(s)"""

    with codecs.open(NODES_PATH, 'w') as nodes_file, \
         codecs.open(NODE_TAGS_PATH, 'w') as nodes_tags_file, \
         codecs.open(WAYS_PATH, 'w') as ways_file, \
         codecs.open(WAY_NODES_PATH, 'w') as way_nodes_file, \
         codecs.open(WAY_TAGS_PATH, 'w') as way_tags_file:

        nodes_writer = UnicodeDictWriter(nodes_file, NODE_FIELDS)
        node_tags_writer = UnicodeDictWriter(nodes_tags_file, NODE_TAGS_FIELDS)
        ways_writer = UnicodeDictWriter(ways_file, WAY_FIELDS)
        way_nodes_writer = UnicodeDictWriter(way_nodes_file, WAY_NODES_FIELDS)
        way_tags_writer = UnicodeDictWriter(way_tags_file, WAY_TAGS_FIELDS)

        nodes_writer.writeheader()
        node_tags_writer.writeheader()
        ways_writer.writeheader()
        way_nodes_writer.writeheader()
        way_tags_writer.writeheader()

        validator = cerberus.Validator()

        for element in get_element(file_in, tags=('node', 'way')):
            el = shape_element(element)
            if el:
                if validate is True:
                    validate_element(el, validator)

                if element.tag == 'node':
                    nodes_writer.writerow(el['node'])
                    node_tags_writer.writerows(el['node_tags'])
                elif element.tag == 'way':
                    ways_writer.writerow(el['way'])
                    way_nodes_writer.writerows(el['way_nodes'])
                    way_tags_writer.writerows(el['way_tags'])


if __name__ == '__main__':
    # Note: Validation is ~ 10X slower. For the project consider using a small
    # sample of the map when validating.
    process_map(OSM_PATH, validate=False)
