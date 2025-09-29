export const initialLegendConfig = {
    file: 'Sample Diagram.vsdx',
    pages_to_process: [{ page_index: 0 }],
    diagram_config: {
        default_shape_condition: {
            parsed_shape_name: 'MainShape',
        },
        shape_references: [
            {
                diagram_master_shape_name: 'Decision/Checkpoint',
                shape_conditions: [
                    {
                        parsed_shape_name: 'DecisionDiamond',
                        property_sources: [
                            {
                                property_name: 'text',
                                mapping: [
                                    {
                                        source: [{ visio_shape_data_label: 'Checkpoint Text' }],
                                    },
                                ],
                            },
                        ],
                    },
                ],
            },
            {
                diagram_shape_name: 'Prompt_',
                shape_conditions: [
                    {
                        parsed_shape_name: 'SayBox',
                        property_sources: [
                            {
                                property_name: 'text',
                                mapping: [{ source: [{ visio_shape_data_label: 'Node' }] }],
                            },
                            {
                                property_name: 'agent_says',
                                mapping: [
                                    { source: [{ visio_shape_data_label: 'InitialPrompt' }] },
                                ],
                            },
                        ],
                    },
                ],
            },
            {
                diagram_master_shape_name: 'say_',
                shape_conditions: [
                    {
                        parsed_shape_name: 'SayBox',
                        property_sources: [
                            {
                                property_name: 'text',
                                mapping: [{ source: [{ visio_shape_data_label: 'Node' }] }],
                            },
                            {
                                property_name: 'agent_says',
                                mapping: [
                                    { source: [{ visio_shape_data_label: 'Initial' }] },
                                ],
                            },
                        ],
                    },
                ],
            },
            {
                diagram_shape_name: 'API',
                shape_conditions: [
                    {
                        parsed_shape_name: 'Webhook',
                        property_sources: [
                            {
                                property_name: 'text',
                                mapping: [
                                    { source: [{ visio_shape_data_label: 'APIName' }] },
                                ],
                            },
                        ],
                    },
                ],
            },
            {
                diagram_master_shape_name: 'UnLabeledArc',
                shape_conditions: [
                    {
                        parsed_shape_name: 'Line',
                        regex_match: { regex: '^([^,]*)' },
                        property_sources: [
                            {
                                property_name: 'text',
                                mapping: [
                                    {
                                        source: [{ attribute_name: 'text' }],
                                        regex_extract: '^([^,]*)',
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        parsed_shape_name: 'Line',
                        property_sources: [
                            {
                                property_name: 'text',
                                mapping: [{ source: [{ attribute_name: 'text' }] }],
                            },
                        ],
                    },
                ],
            },
            {
                diagram_shape_name: 'External Application',
                shape_conditions: [
                    {
                        parsed_shape_name: 'OffPageReference',
                        property_sources: [
                            {
                                property_name: 'text',
                                mapping: [
                                    {
                                        source: [
                                            { visio_shape_data_label: 'Application Name' },
                                        ],
                                    },
                                    { source: [{ text: ' (' }] },
                                    {
                                        source: [{ visio_shape_data_label: 'Parameter List' }],
                                    },
                                    { source: [{ text: ')' }] },
                                ],
                            },
                            {
                                property_name: 'flow_display_name',
                                mapping: [
                                    {
                                        source: [
                                            { visio_shape_data_label: 'Application Name' },
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                ],
            },
            {
                diagram_shape_name: 'Off Page Reference',
                shape_conditions: [
                    {
                        parsed_shape_name: 'OffPageReference',
                        regex_match: { regex: '^Go to\\s*' },
                        property_sources: [
                            {
                                property_name: 'text',
                                mapping: [{ source: [{ attribute_name: 'text' }] }],
                            },
                            {
                                property_name: 'flow_display_name',
                                mapping: [
                                    {
                                        source: [{ attribute_name: 'text' }],
                                        regex_extract: '^Go to\\s*([\\S\\s]*)',
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        parsed_shape_name: 'OffPageReference',
                        regex_match: { regex: '^Return to\\s*' },
                        property_sources: [
                            {
                                property_name: 'conditional',
                                mapping: [{ source: [{ boolean: 'true' }] }],
                            },
                            {
                                property_name: 'text',
                                mapping: [{ source: [{ attribute_name: 'text' }] }],
                            },
                            {
                                property_name: 'flow_display_name',
                                mapping: [
                                    {
                                        source: [{ attribute_name: 'text' }],
                                        regex_extract: '^Return to\\s*([\\S\\s]*)',
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        parsed_shape_name: 'OffPageReference',
                        regex_match: { regex: '^From\\s*' },
                        property_sources: [
                            {
                                property_name: 'entry',
                                mapping: [{ source: [{ boolean: 'true' }] }],
                            },
                            {
                                property_name: 'conditional',
                                mapping: [{ source: [{ boolean: 'true' }] }],
                            },
                            {
                                property_name: 'text',
                                mapping: [{ source: [{ attribute_name: 'text' }] }],
                            },
                            {
                                property_name: 'flow_display_name',
                                mapping: [
                                    {
                                        source: [{ attribute_name: 'text' }],
                                        regex_extract: '^From\\s*([\\S\\s]*)',
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        parsed_shape_name: 'OffPageReference',
                        regex_match: { regex: '^Return from\\s*' },
                        property_sources: [
                            {
                                property_name: 'entry',
                                mapping: [{ source: [{ boolean: 'true' }] }],
                            },
                            {
                                property_name: 'conditional',
                                mapping: [{ source: [{ boolean: 'true' }] }],
                            },
                            {
                                property_name: 'text',
                                mapping: [{ source: [{ attribute_name: 'text' }] }],
                            },
                            {
                                property_name: 'flow_display_name',
                                mapping: [
                                    {
                                        source: [{ attribute_name: 'text' }],
                                        regex_extract: '^Return from\\s*([\\S\\s]*)',
                                    },
                                ],
                            },
                        ],
                    },
                ],
            },
            {
                diagram_shape_name: 'Begin/End',
                shape_conditions: [
                    {
                        parsed_shape_name: 'Terminator',
                        property_sources: [
                            {
                                property_name: 'text',
                                mapping: [
                                    { source: [{ attribute_name: 'text' }] },
                                    {
                                        operation: 'OR',
                                        source: [{ visio_shape_data_label: 'Text' }],
                                    },
                                ],
                            },
                        ],
                    },
                ],
            },
            {
                diagram_shape_name: 'Computation State',
                shape_conditions: [
                    {
                        parsed_shape_name: 'ComputationState',
                        property_sources: [
                            {
                                property_name: 'text',
                                search_children: true,
                                mapping: [{ source: [{ attribute_name: 'text' }] }],
                            },
                            {
                                property_name: 'parameter_action',
                                search_children: true,
                                mapping: [
                                    {
                                        source: [{ attribute_name: 'text' }],
                                        regex_extract: '^Set Flag\\s*([\\S\\s]*)',
                                    },
                                ],
                            },
                        ],
                    },
                ],
            },
            {
                diagram_shape_name: 'Large On Page Ref',
                shape_conditions: [
                    {
                        parsed_shape_name: 'OnPageReferenceExit',
                        property_sources: [
                            {
                                property_name: 'text',
                                mapping: [
                                    { source: [{ visio_shape_data_label: 'ReferenceLabel' }] },
                                ],
                            },
                        ],
                    },
                ],
            },
            {
                diagram_shape_name: 'On Page Reference Small',
                shape_conditions: [
                    {
                        parsed_shape_name: 'OnPageReferenceEntry',
                        property_sources: [
                            {
                                property_name: 'text',
                                search_children: true,
                                mapping: [
                                    { source: [{ visio_shape_data_label: 'ReferenceLabel' }] },
                                ],
                            },
                        ],
                    },
                ],
            },
        ],
    },
};