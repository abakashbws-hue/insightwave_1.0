import { inject } from '@angular/core';
import { AuthService } from './common/services/auth.service';
import { environment } from '../environments/environment';
import { from, switchMap } from 'rxjs';
import { HttpInterceptorFn } from '@angular/common/http';

/**
 * A functional HTTP interceptor that adds an Authorization header to outgoing requests.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const addToken = req.url.startsWith(environment.agentUrl);

  return from(authService.getIdToken()).pipe(
    switchMap((idToken) => {
      if (addToken && idToken) {
        const clonedRequest = req.clone({
          headers: req.headers.set('Authorization', `Bearer ${idToken}`),
        });
        return next(clonedRequest);
      }

      return next(req);
    })
  );
};
