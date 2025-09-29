import { Routes } from '@angular/router';
import { LoginComponent } from './login/login.component';
import { LandingPageComponent } from './landing-page/landing-page.component';
import { authGuard } from './common/guards/auth.guard';
import { ConfirmExitGuard } from './common/guards/confirm-exit.guard';
import { UserProfileChipComponent } from './common/components/user-profile-chip/user-profile-chip.component';
import { ChatComponent } from './common/components/chat/chat.component';

export const routes: Routes = [
  { path: 'login', component: LoginComponent, data: { showLayout: false } },
  { path: 'app', component: LandingPageComponent, canActivate: [authGuard] },
  {
    path: 'user-chip',
    component: UserProfileChipComponent,
    canActivate: [authGuard],
    canDeactivate: [ConfirmExitGuard],
  },
  {
    path: 'chatbot',
    component: ChatComponent,
    canActivate: [authGuard],
  },
  { path: '**', redirectTo: 'app' }, // Optional: wildcard fallback
];
