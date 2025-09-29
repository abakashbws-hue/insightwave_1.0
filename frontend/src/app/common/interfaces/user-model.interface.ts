
export const APP_USERS_COLLECTION = 'appUsers';

export interface AppUser {
  id: string;
  email?: string | null;
  displayName?: string | null;
  photoURL?: string | null;
  lastLoginTime?: string;
}
