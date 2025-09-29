export const initialDialogflowConfig = {
    submit_config: {
        webhook_fail_behavior: 'OMIT',
        intent_fail_behavior: 'OMIT',
        flow_fail_behavior: 'PLACEHOLDER',
    },
    intents: [
        {
            display_name: 'confirmation.yes',
            training_phrases: ['yes', 'yup', 'yeah', 'of course'],
        },
        {
            display_name: 'confirmation.no',
            training_phrases: ['no', 'nope'],
        },
    ],
};