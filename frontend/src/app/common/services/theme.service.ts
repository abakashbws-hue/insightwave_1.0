import { Injectable, Renderer2, RendererFactory2, Inject, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { BehaviorSubject, Observable } from 'rxjs';
import { LocalStorageService } from './local-storage.service';

export type Theme = 'light' | 'dark';

@Injectable({
  providedIn: 'root'
})
export class ThemeService {
  private renderer: Renderer2;
  private themeSubject = new BehaviorSubject<Theme>('light');
  private readonly THEME_KEY = 'preferred-theme';
  private isBrowser: boolean;

  constructor(
    private localStorageService: LocalStorageService,
    private rendererFactory: RendererFactory2,
    @Inject(PLATFORM_ID) private platformId: Object
  ) {
    this.renderer = this.rendererFactory.createRenderer(null, null);

    this.isBrowser = isPlatformBrowser(this.platformId);

    if (this.isBrowser) {
      this.initializeTheme();
    }
  }

  private initializeTheme(): void {
    // This method is now guaranteed to run only in the browser
    const savedTheme = this.localStorageService.get<Theme>(this.THEME_KEY);
    if (savedTheme) {
      this.setTheme(savedTheme, false); // Apply theme without re-saving to localStorage yet
    } else {
      this.setThemeFromSystemPreference(); // This will call setTheme which handles saving
    }
  }

  private setThemeFromSystemPreference(): void {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    this.setTheme(prefersDark ? 'dark' : 'light');
  }

  getTheme(): Observable<Theme> {
    return this.themeSubject.asObservable();
  }

  setTheme(theme: Theme, saveToLocalStorage: boolean = true): void {
    this.themeSubject.next(theme);
    if (this.isBrowser) {
      this.renderer.setAttribute(document.body, 'data-theme', theme);
      if (saveToLocalStorage) {
        this.localStorageService.set(this.THEME_KEY, theme);
      }
    }
  }

  toggleTheme(): void {
    const currentTheme = this.themeSubject.value;
    this.setTheme(currentTheme === 'light' ? 'dark' : 'light');
  }

  // Listen for system theme changes
  watchSystemTheme(): void {
    if (this.isBrowser) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        // Only update if the user hasn't manually set a theme (i.e., no theme in localStorage)
        if (this.localStorageService.get(this.THEME_KEY) === null) {
          this.setTheme(e.matches ? 'dark' : 'light');
        }
      });
    }
  }
} 