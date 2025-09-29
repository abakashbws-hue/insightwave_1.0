import { Component, Inject, Input } from '@angular/core';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { AgentRunRequest } from '../../models/AgentRunRequest';
import { AgentService } from '../../services/agent.service';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { CommonModule } from '@angular/common';
import { MatInputModule } from '@angular/material/input';
import { FormsModule, NgModel } from '@angular/forms';

@Component({
  selector: 'app-pending-event-dialog',
  standalone: true,
  templateUrl: './pending-event-dialog.component.html',
  styleUrl: './pending-event-dialog.component.scss',
  imports: [
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    CommonModule,
    MatInputModule,
    MatFormFieldModule,
    FormsModule,
  ],
})
export class PendingEventDialogComponent {
  selectedEvent: any = null;
  app_name: string;
  user_id: string;
  session_id: string;
  function_call_event_id: string;
  sending: boolean = false;

  constructor(
    public dialogRef: MatDialogRef<PendingEventDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any,
    private agentService: AgentService
  ) {
    this.selectedEvent = data.event;
    this.app_name = data.app_name;
    this.user_id = data.user_id;
    this.session_id = data.session_id;
    this.function_call_event_id = data.function_call_event_id;
  }

  argsToJson(args: any) {
    return JSON.stringify(args);
  }

  sendResponse() {
    this.sending = true;
    const req: AgentRunRequest = {
      app_name: this.app_name,
      user_id: this.user_id,
      session_id: this.session_id,
      new_message: {
        role: 'user',
        parts: [],
      },
    };
    if (this.selectedEvent.response) {
      req.function_call_event_id = this.function_call_event_id;
      req.new_message.parts.push({
        function_response: {
          id: this.selectedEvent.id,
          name: this.selectedEvent.name,
          response: { response: this.selectedEvent.response },
        },
      });
    }
    this.agentService.run(req).subscribe((res) => {
      this.sending = false;
      for (const e of res) {
        if (e.content.parts[0].text) {
          this.dialogRef.close({
            text: e.content.parts[0].text,
            events: [this.selectedEvent],
          });
        }
      }
    });
  }
}
