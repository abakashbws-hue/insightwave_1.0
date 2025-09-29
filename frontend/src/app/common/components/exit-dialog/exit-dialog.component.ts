import { Component, Inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogRef, MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';

export interface ExitDialogData {
  title?: string;
  message: string;
  confirmButtonText?: string;
  cancelButtonText?: string;
}

@Component({
  selector: 'app-exit-dialog',
  standalone: true,
  imports: [MatDialogModule, MatButtonModule],
  templateUrl: './exit-dialog.component.html',
  styleUrl: './exit-dialog.component.scss',
})
export class ExitDialogComponent {
  // Default values
  title = 'Unsaved Changes';
  message =
    'You have unsaved changes. Are you sure you want to leave this page?';
  confirmButtonText = 'Leave';
  cancelButtonText = 'Stay';

  constructor(
    public dialogRef: MatDialogRef<ExitDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: ExitDialogData
  ) {
    if (data?.title) this.title = data.title;
    if (data?.message) this.message = data.message;
    if (data?.confirmButtonText)
      this.confirmButtonText = data.confirmButtonText;
    if (data?.cancelButtonText) this.cancelButtonText = data.cancelButtonText;
  }

  onConfirm(): void {
    this.dialogRef.close(true);
  }

  onCancel(): void {
    this.dialogRef.close(false);
  }
}
