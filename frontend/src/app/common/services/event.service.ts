import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { URLUtil } from '../utils/url-util';

@Injectable({
  providedIn: 'root',
})
export class EventService {
  apiServerDomain = URLUtil.getApiServerBaseUrl();
  constructor(private http: HttpClient) {}

  getEventTrace(id: string) {
    const url = this.apiServerDomain + `/debug/trace/${id}`;
    return this.http.get<any>(url);
  }

  getEvent(
    userId: string,
    appName: string,
    sessionId: string,
    eventId: string
  ) {
    const url =
      this.apiServerDomain +
      `/apps/${appName}/users/${userId}/sessions/${sessionId}/events/${eventId}/graph`;
    return this.http.get<{ dot_src?: string }>(url);
  }
}
