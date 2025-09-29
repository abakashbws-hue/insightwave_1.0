import { Component, Inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';

export interface DeleteSessionDialogData {
  title: string;
  message: string;
  confirmButtonText: string;
  cancelButtonText: string;
}

@Component({
  selector: 'app-delete-session-dialog',
  standalone: true,
  imports: [MatDialogModule, MatButtonModule],
  templateUrl: './delete-session-dialog.component.html',
  styleUrl: './delete-session-dialog.component.scss',
})
export class DeleteSessionDialogComponent {
  constructor(
    public dialogRef: MatDialogRef<DeleteSessionDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: DeleteSessionDialogData
  ) {}

  onConfirm(): void {
    this.dialogRef.close(true);
  }

  onCancel(): void {
    this.dialogRef.close(false);
  }
}
