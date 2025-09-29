import { Component, Inject, OnInit } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-video-dialog',
  standalone: true,
  imports: [ CommonModule, MatDialogModule, MatIconModule ],
  templateUrl: './video-dialog.component.html',
  styleUrl: './video-dialog.component.scss'
})
export class VideoDialogComponent implements OnInit {
  // Properties for the video dialog
  safeVideoUrl: SafeResourceUrl | null = null;
  videoTitle: string = 'Demo Video';

  constructor(
    public dialogRef: MatDialogRef<VideoDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { videoUrl: string, title?: string },
    private sanitizer: DomSanitizer
  ) {}

  ngOnInit(): void {
    if (this.data?.videoUrl) {
      // Sanitize the URL to prevent XSS attacks when binding to iframe src
      this.safeVideoUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.data.videoUrl);
      this.videoTitle = this.data.title || this.videoTitle;
    } else {
      console.error("VideoDialogComponent: No video URL provided.");
      this.closeDialog(); // Close if no URL
    }
  }

  closeDialog(): void {
    this.dialogRef.close();
  }
}
