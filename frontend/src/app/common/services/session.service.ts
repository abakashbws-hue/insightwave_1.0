import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { URLUtil } from '../utils/url-util';

@Injectable({
  providedIn: 'root',
})
export class SessionService {
  apiServerDomain = URLUtil.getApiServerBaseUrl();
  constructor(private http: HttpClient) {}

  createSession(userId: string, appName: string) {
    if (this.apiServerDomain != undefined) {
      const url =
        this.apiServerDomain + `/apps/${appName}/users/${userId}/sessions`;
      return this.http.post<any>(url, null);
    }
    return new Observable<any>();
  }

  listSessions(userId: string, appName: string) {
    if (this.apiServerDomain != undefined) {
      const url =
        this.apiServerDomain + `/apps/${appName}/users/${userId}/sessions`;

      return this.http.get<any>(url);
    }
    return new Observable<[]>();
  }

  deleteSession(userId: string, appName: string, sessionId: string) {
    const url =
      this.apiServerDomain +
      `/apps/${appName}/users/${userId}/sessions/${sessionId}`;

    return this.http.delete<any>(url);
  }

  getSession(userId: string, appName: string, sessionId: string) {
    const url =
      this.apiServerDomain +
      `/apps/${appName}/users/${userId}/sessions/${sessionId}`;

    return this.http.get<any>(url);
  }
}
