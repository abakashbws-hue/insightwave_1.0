import { Component, Input } from '@angular/core';
import { CardData } from '../../../card-data.interface';
import { MatIconModule } from '@angular/material/icon';
import { RouterModule } from '@angular/router';
import { CommonModule } from '@angular/common';
import { VideoDialogComponent } from '../video-dialog/video-dialog.component';
import { MatDialog } from '@angular/material/dialog';
import { MatTooltipModule } from '@angular/material/tooltip';

@Component({
  selector: 'app-card',
  templateUrl: './card.component.html',
  styleUrls: ['./card.component.scss'],
  standalone: true,
  imports: [CommonModule, MatIconModule, MatTooltipModule, RouterModule],
})

export class CardComponent{
  @Input() card: CardData | undefined;

  cropDescription: boolean = true;

  constructor(private dialog: MatDialog) {} // Inject MatDialog

  ngOnInit(): void {}

  // Method to open the video dialog
  openVideoDialog(videoUrl: string | undefined, title: string | undefined): void {
    if (!videoUrl) {
      console.error("Cannot open video dialog: No URL provided.");
      return;
    }

    // Ensure the URL ends with /preview for Google Drive embedding
    let embedUrl = videoUrl;
    if (embedUrl.includes('drive.google.com/file/d/') && !embedUrl.endsWith('/preview')) {
        if (embedUrl.includes('?')) { // Handle existing query params like resourcekey
          const parts = embedUrl.split('?');
          embedUrl = `${parts[0]}/preview?${parts[1]}`;
        } else {
          embedUrl = `${embedUrl}/preview`;
        }
    }


    this.dialog.open(VideoDialogComponent, {
      maxWidth: '1000px',
      data: {
        videoUrl: embedUrl,
        title: title || 'Demo video',
      },
      panelClass: 'video-dialog-container'
    });
  }
}
