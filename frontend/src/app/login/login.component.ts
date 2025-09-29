import { Component, inject } from '@angular/core';
import { SpinnerComponent } from '../common/components/spinner/spinner.component';
import { NgIf } from '@angular/common';
import { Auth, GoogleAuthProvider, signInWithPopup, User } from '@angular/fire/auth';
import { Router } from '@angular/router';
import { AuthService } from '../common/services/auth.service';
import { FirestoreDataService } from '../common/services/firestore-data.service';
import { firstValueFrom } from 'rxjs';
import { LocalStorageService } from '../common/services/local-storage.service';
import { APP_USERS_COLLECTION, AppUser } from '../common/interfaces/user-model.interface';
import { LOGGED_IN_USER_PROFILE, USER_SESSION_ACTIVE } from '../common/utils/constants';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
  standalone: true,
  imports: [SpinnerComponent, NgIf],
})
export class LoginComponent {
  loader: boolean = false;
  private auth: Auth = inject(Auth);
  private router: Router = inject(Router);
  private authService: AuthService = inject(AuthService);
  private firestoreService: FirestoreDataService = inject(FirestoreDataService);
  private localStorageService: LocalStorageService = inject(LocalStorageService);

  constructor() {
    this.redirectToHomeIfLoggedIn();
  }

  async loginWithGoogle() {
    this.loader = true;
    try {
      const provider = new GoogleAuthProvider();
      const result = await signInWithPopup(this.auth, provider);
      const user = result.user;

      if (user) {
        // Check if user exists in Firestore and add if not
        await this.checkAndAddUser(user);

        // Store essential user info in local storage
        const userProfile: AppUser = {
          id: user.uid,
          email: user.email,
          displayName: user.displayName,
          photoURL: user.photoURL,
        };
        this.localStorageService.set<AppUser>(LOGGED_IN_USER_PROFILE, userProfile as AppUser);

        const SESSION_DURATION_SECONDS = 60 * 60 * 24 * 7; // 7 days
        this.localStorageService.set<boolean>(USER_SESSION_ACTIVE, true, SESSION_DURATION_SECONDS);

        // Successfully logged in and user data handled, navigate to home
        await this.router.navigate(['/app']);
      } else {
         // Handle case where user is null unexpectedly after successful popup
         console.warn('Google sign-in successful, but user object is null.');
      }
    } catch (error) {
      console.error('Error during Google sign-in:', error);
    } finally {
      this.loader = false;
    }
  }

  /**
   * Checks if the user exists in the 'users' collection and adds them if not.
   * Updates existing user's display name, photo URL, and last login time. if they have changed.
   * @param user The Firebase Auth User object.
   */
  private async checkAndAddUser(user: User): Promise<void> {
    const now = new Date().toISOString(); // Get current time once

    try {
      const existingUser = await this.firestoreService.getRecordById<AppUser>(APP_USERS_COLLECTION, user.uid);

      if (!existingUser) {
        console.log(`User ${user.uid} not found in Firestore. Adding...`);
        // Prepare data for a new user, including lastLoginTime
        const newUserProfileData: Omit<AppUser, 'id'> = {
          email: user.email,
          displayName: user.displayName,
          photoURL: user.photoURL,
          lastLoginTime: now, 
        };
        await this.firestoreService.setRecordWithId<AppUser>(
          APP_USERS_COLLECTION,
          user.uid,
          newUserProfileData
        );
        console.log(`User ${user.uid} added successfully.`);
      } else {
        console.log(`User ${user.uid} already exists in Firestore. Checking for updates...`);
        // Prepare potential updates, excluding 'id'
        const updatedData: Partial<Omit<AppUser, 'id'>> = {
          lastLoginTime: now
        };

        // Check if other profile details changed
        if (existingUser.displayName !== user.displayName) {
          updatedData.displayName = user.displayName;
        }
        if (existingUser.photoURL !== user.photoURL) {
          updatedData.photoURL = user.photoURL;
        }

        // If there are changes, update the record
        if (Object.keys(updatedData).length > 0) {
          await this.firestoreService.updateRecord<AppUser>(APP_USERS_COLLECTION, user.uid, updatedData);
          console.log(`User ${user.uid} data updated.`);
        } else {
          console.log(`User ${user.uid} data is already up-to-date.`);
        }
      }
    } catch (error) {
      console.error(`Error checking or managing user ${user.uid} in Firestore:`, error);
    }
  }


  async redirectToHomeIfLoggedIn() {
    const isAuthenticated = await firstValueFrom(
      this.authService.isAuthenticated()
    );

    if (isAuthenticated) {
      this.router.navigate(['/app']);
    }
  }
}
