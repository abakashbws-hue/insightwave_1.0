import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-user-profile-chip',
  standalone: true,
  imports: [],
  templateUrl: './user-profile-chip.component.html',
  styleUrl: './user-profile-chip.component.scss'
})

export class UserProfileChipComponent {
  @Input() userProfileImageUrl: string | null = 'assets/images/profile-pic.png';
  @Input() userDisplayName: string = 'User';

  handleImageError() {
    this.userProfileImageUrl = 'assets/images/profile-pic.png';
    console.warn(`Failed to load image for ${this.userDisplayName}. Using default.`);
  }

  get userAltText(): string {
    return `Photo of ${this.userDisplayName || 'User'}`;
  }
}
