import { Injectable, NgZone, inject } from '@angular/core';
import { Auth, User, onAuthStateChanged } from '@angular/fire/auth';
import { Router } from '@angular/router';
import { BehaviorSubject, Observable, ReplaySubject, filter, firstValueFrom, map, take } from 'rxjs';
import { environment } from '../../../environments/environment';
import { MatDialog } from '@angular/material/dialog';
import { LocalStorageService } from './local-storage.service';
import { SessionExpiredDialogComponent } from '../components/session-expired-dialog/session-expired-dialog.component';
import { LOGGED_IN_USER_PROFILE, USER_SESSION_ACTIVE } from '../utils/constants';

// Declare google for Google Identity Services (GIS)
declare var google: any;

const GOOGLE_GIS_SCRIPT_ID = 'google-gis-script';
const GOOGLE_GIS_SCRIPT_URL = 'https://accounts.google.com/gsi/client';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private auth = inject(Auth);
  private router = inject(Router);
  private ngZone = inject(NgZone);
  private localStorageService = inject(LocalStorageService);
  private dialog = inject(MatDialog);

  private userSubject = new BehaviorSubject<User | null | undefined>(undefined);
  user$ = this.userSubject.asObservable();

  isLoading$ = this.user$.pipe(
    map(user => user === undefined)
  );

  private gisScriptLoaded = new ReplaySubject<boolean>(1); // To signal GIS script load status

  private isProcessingSessionExpiry = false;

  constructor() {
    this.loadGisScript();
    this.handleInitialAuthAndSessionCheck();
    this.subscribeToLocalStorageExpiry();
  }
  
  private loadGisScript() {
    // Check if running in a browser environment
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      this.gisScriptLoaded.next(false);
      return;
    }

    if (document.getElementById(GOOGLE_GIS_SCRIPT_ID)) {
      // Script tag exists, check if google.accounts is ready
      if (typeof google !== 'undefined' && google.accounts && google.accounts.oauth2) {
        this.gisScriptLoaded.next(true);
      }
      // If not ready, onload callback will handle it or it might still be loading.
      return;
    }

    const script = document.createElement('script');
    script.id = GOOGLE_GIS_SCRIPT_ID;
    script.src = GOOGLE_GIS_SCRIPT_URL;
    script.async = true;
    script.defer = true;
    script.onload = () => {
      this.ngZone.run(() => {
        if (typeof google !== 'undefined' && google.accounts && google.accounts.oauth2) {
          console.log('Google Identity Services script loaded and ready.');
          this.gisScriptLoaded.next(true);
        } else {
          console.error('GIS script loaded, but google.accounts.oauth2 not available.');
          this.gisScriptLoaded.next(false);
        }
      });
    };
    script.onerror = () => {
      this.ngZone.run(() => {
        console.error('Failed to load Google Identity Services script.');
        this.gisScriptLoaded.next(false);
      });
    };
    document.head.appendChild(script);
  }

  /**
   * Retrieves a Google Cloud Platform OAuth 2.0 access token.
   * This method uses Google Identity Services (GIS) to obtain the token.
   * Ensure your GCP project has an OAuth 2.0 Web Client ID configured
   * in `environment.gcpOauthClientId` and the necessary Authorized JavaScript Origins
   * in the Google Cloud Console for that Client ID.
   *
   * @param scopes - An array of OAuth scopes required for the Google Cloud APIs.
   *                 Example: ['https://www.googleapis.com/auth/dialogflow']
   * @returns A Promise resolving with the access token string, or null if an error occurs.
   */
  async getGcpAccessToken(scopes: string[]): Promise<string | null> {
    const firebaseUser = this.userSubject.getValue();
    if (!firebaseUser) {
      console.warn('No Firebase user logged in. Cannot get GCP access token.');
      return null;
    }

    const scriptReady = await firstValueFrom(this.gisScriptLoaded);

    if (!scriptReady || typeof google === 'undefined' || !google.accounts || !google.accounts.oauth2) {
      console.error('Google Identity Services not available or failed to load.');
      return null;
    }

    if (!environment.gcpOauthClientId || environment.gcpOauthClientId.startsWith('YOUR_')) {
      console.error('GCP OAuth Client ID is not configured correctly in environment variables.');
      return null;
    }

    return new Promise<string | null>((resolve) => {
      try {
        const tokenClient = google.accounts.oauth2.initTokenClient({
          client_id: environment.gcpOauthClientId,
          scope: scopes.join(' '),
          callback: (tokenResponse: any) => this.ngZone.run(() => {
            if (tokenResponse && tokenResponse.access_token) {
              resolve(tokenResponse.access_token);
            } else {
              console.error('GCP Access Token not found in GIS response:', tokenResponse);
              resolve(null);
            }
          }),
          error_callback: (error: any) => this.ngZone.run(() => {
            console.error('Error requesting GCP Access Token via GIS:', error);
            resolve(null);
          }),
          hint: firebaseUser.email || undefined,
        });
        tokenClient.requestAccessToken({ prompt: '' }); // Attempt silent or minimal prompt. Use 'consent' to force.
      } catch (error) {
        this.ngZone.run(() => {
          console.error('Error initializing or using GIS token client:', error);
          resolve(null);
        });
      }
    });
  }

  async signOut(sessionExpired: boolean = false) {
    if (sessionExpired) {
      if (this.isProcessingSessionExpiry) {
        console.warn('AuthService: signOut(sessionExpired=true) called while already processing session expiry. Ignoring subsequent call.');
        return; // Prevent re-entry
      }
      this.isProcessingSessionExpiry = true;
    }
    try {
      await this.auth.signOut();
      this.localStorageService.remove(LOGGED_IN_USER_PROFILE);
      this.localStorageService.remove(USER_SESSION_ACTIVE);

      if (sessionExpired) {
        console.log('AuthService: Opening session expired dialog.');
        const dialogRef = this.dialog.open(SessionExpiredDialogComponent, {
          width: '400px',
          disableClose: true,
          data: {
            title: 'Session Expired',
            message: 'Your session has timed out. Please log in again to continue.',
            buttonText: 'Log In'
          }
        });
        // Navigate to login after the dialog is closed
        dialogRef.afterClosed().subscribe(() => {
          this.router.navigate(['/login'])
            .catch(navError => console.error('AuthService: Navigation to login after dialog failed.', navError))
            .finally(() => {
              this.isProcessingSessionExpiry = false;
            });
        });
      } else {
        // If not a session expiry, navigate directly
        await this.router.navigate(['/login']);
        // If a non-session-expired signout happens, ensure the flag is reset.
        if (this.isProcessingSessionExpiry) {
            console.warn("AuthService: isProcessingSessionExpiry was true during a non-session-expired signOut. Resetting.");
            this.isProcessingSessionExpiry = false;
        }
      }
    } catch (error) {
      console.error('Error signing out:', error);
      // Fallback navigation if something goes wrong or not a session expiry
      this.router.navigate(['/login'])
        .catch(navError => console.error('AuthService: Fallback navigation to login failed.', navError))
        .finally(() => {
          if (sessionExpired) { // Only reset if it was set for this flow
            console.log('AuthService: Resetting isProcessingSessionExpiry flag in catch block.');
            this.isProcessingSessionExpiry = false;
          }
        });

    }
  }

  private handleInitialAuthAndSessionCheck(): void {
    this.user$.pipe(
      filter(user => user !== undefined), // Wait until initial auth state is known (not undefined)
      take(1)                             // Perform this check only once on startup
    ).subscribe(firebaseUser => {
      this.ngZone.run(() => {
        if (firebaseUser) {
          const isSessionMarkerValid = this.localStorageService.get<boolean>(USER_SESSION_ACTIVE);

          // For detailed debugging:
          // console.log('[AuthService - InitialCheck] Firebase User ID:', firebaseUser.uid);
          // console.log('[AuthService - InitialCheck] Value of isSessionMarkerValid (from LS.get):', isSessionMarkerValid);
          const rawItem = localStorage.getItem(`${this.localStorageService['currentNamespace']}:userSessionActive`); // Accessing namespace for debug
          if (rawItem) {
            try {
              const parsed = JSON.parse(rawItem);
              // More detailed debugging:
              // console.log('[AuthService - InitialCheck] Raw LS item parsed:', parsed);
              // if (parsed.expiry) {
              //   console.log('[AuthService - InitialCheck] Stored Expiry Time:', new Date(parsed.expiry).toISOString(), `(${parsed.expiry})`);
              //   console.log('[AuthService - InitialCheck] Current Time:', new Date(Date.now()).toISOString(), `(${Date.now()})`);
              //   console.log('[AuthService - InitialCheck] Is raw item expired (expiry < now)?', parsed.expiry < Date.now());
              // }
            } catch (e) { console.error("Error parsing raw LS item for debug", e); }
          } else {
            console.log('[AuthService - InitialCheck] Raw LS item "userSessionActive" not found.');
          }

          if (!isSessionMarkerValid) { // isSessionMarkerValid will be null if item expired and was removed by .get()
            console.log('AuthService (Initial App Load Check): Firebase user exists, but local session marker is invalid/expired. Logging out.');
            this.signOut(true); // Pass true for sessionExpired
          } else {
            console.log('[AuthService - InitialCheck] Local session marker is valid. No automatic logout needed.');
          }
        } else {
          console.log('[AuthService - InitialCheck] No Firebase user. Ensuring local session items are cleared.');
          this.localStorageService.remove(LOGGED_IN_USER_PROFILE);
          this.localStorageService.remove(USER_SESSION_ACTIVE);
        }
      });
    });

    // This listener keeps the userSubject updated and handles explicit Firebase logouts
    // (e.g., token revoked by server, user deleted from Firebase console).
    onAuthStateChanged(this.auth, (user) => {
        this.ngZone.run(() => {
            this.userSubject.next(user);
            if (!user) {
                console.log('[AuthService - onAuthStateChanged] Firebase reported user is null. Clearing local session items.');
                this.localStorageService.remove(LOGGED_IN_USER_PROFILE);
                this.localStorageService.remove(USER_SESSION_ACTIVE);
            }
        });
    });
  }

  private subscribeToLocalStorageExpiry(): void {
    this.localStorageService.itemExpired$.subscribe(expiredKey => {
      this.ngZone.run(() => { // Ensure operations are within Angular's zone
        if (expiredKey === USER_SESSION_ACTIVE) {
          console.log('AuthService: Detected "userSessionActive" key expired via LocalStorageService event.');
          // Check if a user is currently considered logged in by Firebase
          // to avoid trying to "log out" someone who isn't logged in.
          const currentUser = this.userSubject.getValue();
          if (currentUser) {
            console.log('AuthService: Firebase user exists. Initiating sign out due to session marker expiry.');
            this.signOut(true); // Pass true for sessionExpired
          }
        }
      });
    });
  }

  getIdToken() {
    return this.auth.currentUser?.getIdToken() || '';
  }

  isAuthenticated(): Observable<boolean> {
    return this.user$.pipe(
      filter(user => user !== undefined),
      map(user => user !== null)
    );
  }

  getLoggedInUser(): Observable<User | null | undefined> {
    return this.user$;
  }
}