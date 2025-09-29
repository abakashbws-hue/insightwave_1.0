export interface AgentRunRequest {
  app_name: string;
  user_id: string;
  session_id: string;
  new_message: any;
  function_call_event_id?: string;
  streaming?: boolean;
}
