import { Component, Inject } from '@angular/core';
import {
  MatDialogRef,
  MAT_DIALOG_DATA,
  MatDialogModule,
} from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { CommonModule } from '@angular/common';

export interface SessionExpiredDialogData {
  title?: string;
  message?: string;
  buttonText?: string;
}

@Component({
  selector: 'app-session-expired-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule, MatButtonModule],
  templateUrl: './session-expired-dialog.component.html',
  styleUrls: ['./session-expired-dialog.component.scss'],
})
export class SessionExpiredDialogComponent {
  title: string;
  message: string;
  buttonText: string;

  constructor(
    public dialogRef: MatDialogRef<SessionExpiredDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: SessionExpiredDialogData
  ) {
    this.title = data?.title || 'Session Expired';
    this.message = data?.message || 'Your session has timed out. Please log in again to continue.';
    this.buttonText = data?.buttonText || 'OK';
  }

  onOk(): void {
    this.dialogRef.close();
  }
}