# -*- coding: utf-8 -*-

"""
    NestedFormat layout engine
    ------------------------

    In this layout for each nesting level is a new div

    :copyright: Copyright 2017, Leo Noordergraaf, Copyright 2018, NVISO
    :licence: GPL v3, see LICENCE for details.
"""

from docutils import nodes
from docutils.nodes import fully_normalize_name as normalize_name, Text, field, field_name, field_body, \
    field_list, bullet_list, list_item, paragraph
from docutils.statemachine import ViewList


class NestedFormat(object):

    KV_SIMPLE = {
        'multipleOf': 'Multiple of',
        'maximum': 'Maximum',
        'exclusiveMaximum': 'Exclusive Maximum',
        'minimum': 'Minimum',
        'exclusiveMinimum': 'Exclusive Minimum',
        'maxLength': 'Maximum length',
        'minLength': 'Minimum length',
        'pattern': 'Pattern',
        'default': 'Default',
        'format': 'Format'}

    KV_ARRAY = {'maxItems': 'Maximum number of items',
                'minItems': 'Minimum number of items',
                'uniqueItems': 'Unique items'}

    KV_OBJECT = {'maxProperties': 'Maximum number of properties',
                 'minProperties': 'Minimum number of properties'}

    COMBINATORS = {'allOf': 'All of', 'anyOf': 'Any of', 'oneOf': 'One of'}

    SINGLEOBJECTS = {'not': 'Not'}

    def __init__(self, state, lineno, app):
        super(NestedFormat, self).__init__()
        self.app = app
        self.trans = None
        self.lineno = lineno
        self.state = state
        self.nesting = 0

    def transform(self, schema):
        body = self._dispatch(schema)
        return self._wrap_in_section(schema, body)

    def _parse_text(self, text):
        paragraph_node = paragraph()

        vl = ViewList()

        for idx, line in enumerate(text.split("\n")):
            vl.append(line, 'ext', idx)

        self.state.nested_parse(vl, 0, paragraph_node)

        return paragraph_node

    def _process_object_properties(self, schema, prop_name):
        body = field_list()

        for key, item in schema[prop_name].items():
            required_class = ' jsonschema-required' if key in schema.get('required', []) else ''

            inner_body = field_list()

            if key in schema.get('required', []):
                inner_body += self._create_field('Required', 'jsonschema-required', paragraph(text='Yes'))
            else:
                inner_body += self._create_field('Required', 'jsonschema-required', paragraph(text='No'))

            inner_body += self._create_field('Type', 'jsonschema-type', self._dispatch(item))

            body += self._create_field(key, 'jsonschema-property' + required_class, inner_body)

        return body

    def _process_type(self, schema):
        body = field_list()

        if '$$target' in schema:
            body += self._create_field('Id', 'jsonschema-description', [self._create_target(schema),
                                                                        paragraph(text=schema['$$target'])])

        if 'description' in schema:
            description = self._parse_text(schema['description'])
            body += self._create_field('Description', 'jsonschema-description', description)

        if 'type' in schema:
            body += self._create_field('Type', 'jsonschema-description', paragraph(text=schema['type']))

        if schema.get('type') == 'object':

            if 'properties' in schema:
                body += self._create_field('Properties', 'jsonschema-properties',
                                           self._process_object_properties(schema, 'properties'))

            if 'patternProperties' in schema:
                body += self._create_field('Properties', 'jsonschema-pattern-properties',
                                           self._process_object_properties(schema, 'patternProperties'))

            if 'additionalProperties' in schema:
                body += self._bool_or_object(schema['additionalProperties'],
                                             'Additional Properties', 'jsonschema-additional-properties',
                                             {True: 'Allowed', False: 'Not allowed'})

            body.extend(self._kvpairs(schema, self.KV_OBJECT))

        elif schema.get('type') == 'array':

            if 'items' in schema:
                if isinstance(schema['items'], list):
                    enum_items = bullet_list()
                    for item in schema['items']:
                        type_item = list_item()
                        type_item += self._dispatch(item)
                        enum_items += type_item

                    body += self._create_field('Items', 'jsonschema-items', enum_items)
                else:
                    body += self._create_field('Item', 'jsonschema-item-template', self._dispatch(schema['items']))

            if 'additionalItems' in schema:
                body += self._bool_or_object(schema['additionalItems'],
                                             'Additional Items', 'jsonschema-additional-items',
                                             {True: 'Allowed', False: 'Not allowed'})

            body.extend(self._kvpairs(schema, self.KV_ARRAY))

        else:

            if 'enum' in schema:
                enum_items = bullet_list()
                for item in schema['enum']:
                    enum_item = list_item()
                    enum_item += paragraph(text=str(item))
                    enum_items += enum_item
                body += self._create_field('Valid values', 'enum', enum_items)

            body.extend(self._kvpairs(schema, self.KV_SIMPLE))

        return body

    def _process_combinator(self, label, schema):
        entries = bullet_list()

        for subtype in schema:
            entry = list_item()
            entry += self._dispatch(subtype)
            entries += entry

        body = field_list()
        body += self._create_field('Combination', 'json-combinatortype', paragraph(text=label))
        body += self._create_field('Types', 'jsonschema-combinedtypes', entries)

        return body

    def _process_singleobjects(self, label, schema):
        body = field_list()

        body += self._create_field('Combination', 'json-combinatortype', paragraph(text=label))
        body += self._create_field('Types', 'jsonschema-combinedtypes', self._dispatch(schema))

        return body

    def _process_definitions(self, schema):
        def_list = field_list()

        for name, definition in schema.items():
            def_list += self._create_field(name, 'jsonschema-definition', self._dispatch(definition))

        return def_list

    def _dispatch(self, schema):
        # Main driver of the recursive schema traversal.
        if '$ref' in schema:
            return self._process_reftype(schema)
        elif 'type' in schema:
            return self._process_type(schema)
        for k in self.COMBINATORS:
            # combinators belong at this level as alternative to type
            if k in schema:
                return self._process_combinator(self.COMBINATORS[k], schema[k])

        for k in self.SINGLEOBJECTS:
            # combinators belong at this level as alternative to type
            if k in schema:
                return self._process_singleobjects(self.SINGLEOBJECTS[k], schema[k])

        if 'definitions' in schema:
            return self._process_definitions(schema)

        return []

    def _create_target(self, schema):
        # Wrap section and table in a target (anchor) node so
        # that it can be referenced from other sections.
        labels = self.app.env.domaindata['std']['labels']
        anonlabels = self.app.env.domaindata['std']['anonlabels']
        docname = self.app.env.docname
        targets = schema['$$target']
        if not isinstance(targets, list):
            targets = [targets]

        targetnode = nodes.target()
        for target in targets:
            anchor = normalize_name(target)
            targetnode['ids'].append(anchor)
            targetnode['names'].append(anchor)
            anonlabels[anchor] = docname, targetnode['ids'][0]
            labels[anchor] = docname, targetnode['ids'][0], (schema['title'] if 'title' in schema else anchor)
        targetnode.line = self.lineno

        return targetnode

    def _wrap_in_section(self, schema, table):

        result = list()
        if '$$target' in schema:
            result.append(self._create_target(schema))

        if 'title' in schema:
            # Wrap the resulting table in a section giving it a caption and an
            # entry in the table of contents.
            memo = self.state.memo
            mylevel = memo.section_level
            memo.section_level += 1
            section_node = nodes.section()
            textnodes, title_messages = self.state.inline_text(schema['title'], self.lineno)
            titlenode = nodes.title(schema['title'], '', *textnodes)
            name = normalize_name(titlenode.astext())
            section_node['names'].append(name)
            section_node += titlenode
            section_node += title_messages
            self.state.document.note_implicit_target(section_node, section_node)
            section_node += table
            memo.section_level = mylevel
            result.append(section_node)
        else:
            result.append(table)
        return result

    def _process_reftype(self, schema):
        body = field_list()

        if 'description' in schema:
            body += self._create_field('Description', 'jsonschema-description',
                                       self._parse_text(schema['description']))

        body += self._create_field('Reference', 'jsonschema-reference',
                                   self._parse_text(':ref:`'+schema['$ref']+'`'))

        if 'definitions' in schema:
            body += self._create_field('Definitions', 'jsonschema-definitions',
                                       self._process_definitions(schema['definitions']))

        return body

    def _create_field(self, label, clazz, child):
        ret = field()
        ret['classes'].append(clazz)
        ret += field_name(text=label)
        body = field_body()
        body += child
        ret += body

        return ret

    def _objectproperties(self, schema, key):
        # process the `properties` key of the object type
        # used for `properties`, `patternProperties` and
        # `definitions`.
        body = field_list()

        if key in schema:

            for prop in schema[key].keys():
                required = ''
                if 'required' in schema:
                    if prop in schema['required']:
                        required = ' required'
                obj = schema[key][prop]
                body += self._create_field(key, 'type'+required, self._dispatch(obj))
        return body

    def _bool_or_object(self,  schema, label, clazz, options):
        # for those attributes that accept either a boolean or a schema.

        if isinstance(schema, bool):
            return self._create_field(label, clazz, paragraph(text=options[schema]))
        else:
            return self._dispatch(schema)

    def _kvpairs(self, schema, keys):
        # render key-value pairs
        body = []

        for k in keys:
            if k in schema:
                value = schema[k]
                ret = self._create_field(keys[k], 'jsonschema-' + k, paragraph(text=str(value)))
                body.append(ret)

        return body

