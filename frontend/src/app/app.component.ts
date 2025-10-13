import {
  Component,
  OnInit,
  OnDestroy,
  inject,
  HostBinding,
} from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AuthService } from './common/services/auth.service';
import { SpinnerComponent } from './common/components/spinner/spinner.component';
import { CommonModule } from '@angular/common';
import { HeaderComponent } from './common/components/header/header.component';
import { FooterComponent } from './common/components/footer/footer.component';
import { Router, NavigationEnd, ActivatedRoute } from '@angular/router';
import { filter, map, mergeMap, distinctUntilChanged } from 'rxjs/operators';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
  standalone: true,
  imports: [
    RouterOutlet,
    SpinnerComponent,
    CommonModule,
    HeaderComponent,
    FooterComponent,
  ],
})
export class AppComponent implements OnInit, OnDestroy {
  showLayout = true;
  private authService = inject(AuthService);
  isLoading$ = this.authService.isLoading$;
  title = 'insightwave';
  private routerSubscription: Subscription | undefined;
  isChatOpen = false;

  constructor(private router: Router, private activatedRoute: ActivatedRoute) {}

  ngOnInit() {
    this.routerSubscription = this.router.events
      .pipe(
        filter((event) => event instanceof NavigationEnd),
        map(() => {
          let route = this.activatedRoute;
          while (route.firstChild) {
            route = route.firstChild;
          }
          return route;
        }),
        mergeMap((route) => route.data),
        map((data) => data?.['showLayout'] ?? true),
        distinctUntilChanged()
      )
      .subscribe((showLayoutFlag) => {
        this.showLayout = showLayoutFlag;
      });
  }

  ngOnDestroy() {
    this.routerSubscription?.unsubscribe();
  }
}
