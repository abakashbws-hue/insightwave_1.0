import { Component, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../../services/auth.service';
import { AsyncPipe } from '@angular/common';
import { fadeIn, fadeSlideIn } from '../../utils/animations';
import { LocalStorageService } from '../../services/local-storage.service';
import { LOGGED_IN_USER_PROFILE } from '../../utils/constants';
import { AppUser } from '../../interfaces/user-model.interface';
import { map, Observable, of } from 'rxjs';

@Component({
  selector: 'app-hero-section',
  templateUrl: './hero-section.component.html',
  styleUrl: './hero-section.component.scss',
  standalone: true,
  imports: [MatIconModule, AsyncPipe],
  animations: [fadeSlideIn, fadeIn]
})
export class HeroSectionComponent {
  private authService = inject(AuthService);
  user$: Observable<AppUser | null> = of(inject(LocalStorageService).get<AppUser>(LOGGED_IN_USER_PROFILE));

  greetingName$: Observable<string> = this.user$.pipe(
    map(user => {
      if (user?.displayName) {
        const trimmedName = user.displayName.trim();
        if (trimmedName) {
          const parts = trimmedName.split(' ');
          return parts[0];
        }
      }
      return 'there';
    })
  );

  scrollToAutomationTools() {
    const element = document.getElementById('automation-tools');
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
}
