import {
  Component,
  HostListener,
  inject,
  Output,
  EventEmitter,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatButtonModule } from '@angular/material/button';
import { AuthService } from '../../services/auth.service';
import { AsyncPipe, NgIf } from '@angular/common';
import { MatTooltipModule } from '@angular/material/tooltip';
import { FirestoreDataService } from '../../services/firestore-data.service';
import { FEATURE_FLAG_COLLECTION, FeatureFlag } from '../../interfaces/feature-flag.interface';
import { LocalStorageService } from '../../services/local-storage.service';
import { LOGGED_IN_USER_PROFILE } from '../../utils/constants';
import { AppUser } from '../../interfaces/user-model.interface';
import { Observable, of } from 'rxjs';
import { ThemeToggleComponent } from '../../../components/theme-toggle/theme-toggle.component';

@Component({
  selector: 'app-header',
  templateUrl: './header.component.html',
  styleUrl: './header.component.scss',
  standalone: true,
  imports: [
    RouterLink,
    MatIconModule,
    MatMenuModule,
    MatButtonModule,
    AsyncPipe,
    NgIf,
    MatTooltipModule,
    ThemeToggleComponent
  ],
})
export class HeaderComponent {
  private authService = inject(AuthService);
  private firestoreService = inject(FirestoreDataService);
  user$: Observable<AppUser | null> = of(inject(LocalStorageService).get<AppUser>(LOGGED_IN_USER_PROFILE));
  isScrolled = false;

  showAgentChat = false;

  bugReportUrl =
    'https://b.corp.google.com/issues/new?component=1771202&template=2125095';

  constructor() {
    this.firestoreService.getRecordById<FeatureFlag>(FEATURE_FLAG_COLLECTION, 'showAgentChat').then(flag => {
      this.showAgentChat = flag?.isEnabled || false;
    });
  }

  @HostListener('window:scroll', ['$event'])
  onScroll() {
    this.isScrolled = window.scrollY > 0;
  }

  signOut() {
    this.authService.signOut();
  }
}
