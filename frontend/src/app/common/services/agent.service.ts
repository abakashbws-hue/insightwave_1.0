import { HttpClient } from '@angular/common/http';
import { Injectable, NgZone } from '@angular/core';
import { BehaviorSubject, Observable, from } from 'rxjs';
import { URLUtil } from '../utils/url-util';
import { AgentRunRequest } from '../models/AgentRunRequest';
import { AuthService } from '../services/auth.service';
import { switchMap } from 'rxjs/operators';

@Injectable({
  providedIn: 'root',
})
export class AgentService {
  apiServerDomain = URLUtil.getApiServerBaseUrl();
  private _currentApp = new BehaviorSubject<string>('');
  currentApp = this._currentApp.asObservable();

  constructor(private http: HttpClient, private zone: NgZone, private authService: AuthService) {}

  getApp(): Observable<string> {
    return this.currentApp;
  }

  setApp(name: string) {
    this._currentApp.next(name);
  }

  run(req: AgentRunRequest) {
    const headers = {
      'Content-type': 'application/json',
    };
    const options = {
      headers: headers,
    };

    const url = this.apiServerDomain + `/run`;
    return this.http.post<any>(url, req, options);
  }

  run_sse(req: AgentRunRequest) {
    const url = this.apiServerDomain + `/run_sse`;
    return from(this.authService.getIdToken()).pipe(
      switchMap((token: string) => {
        return new Observable<string>((observer) => {
          fetch(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Accept: 'text/event-stream',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify(req),
          })
            .then((response) => {
              const reader = response.body?.getReader();
              const decoder = new TextDecoder('utf-8');
              let lastData: string | null = null;

              const read = () => {
                reader
                  ?.read()
                  .then(({ done, value }) => {
                    if (done) {
                      return observer.complete();
                    }

                    const chunk = decoder.decode(value, { stream: true });
                    const lines = chunk
                      .split(/\r?\n/)
                      .filter((line) => line.startsWith('data: '));
                    lines.forEach((line) => {
                      const data = line.replace(/^data:\s*/, '');
                      this.zone.run(() => observer.next(data));
                    });

                    read(); // Read the next chunk
                  })
                  .catch((err) => {
                    this.zone.run(() => observer.error(err));
                  });
              };

              read();
            })
            .catch((err) => {
              this.zone.run(() => observer.error(err));
            });
        });
      })
    );
  }

listApps(): Observable<string[]> {
    if (this.apiServerDomain == undefined) {
      return new Observable<[]>();
    }
    const url = this.apiServerDomain + `/list-apps?relative_path=./`;

    // FIX: Use 'from(getIdToken)' to get the token and attach it to the request
    return from(this.authService.getIdToken()).pipe(
      switchMap((token: string) => {
        const headers = {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}` // CRITICAL: Add Auth Token
        };
        return this.http.get<string[]>(url, { headers: headers });
      })
    );
  }
}
