import { Component, EventEmitter, Input, OnChanges, OnInit, Output, SimpleChanges } from '@angular/core';
import { Subject, of } from 'rxjs';
import { catchError, filter, switchMap } from 'rxjs/operators';
import { Session } from '../../models/Session';
import { SessionService } from '../../services/session.service';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-session-tab',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './session-tab.component.html',
  styleUrl: './session-tab.component.scss',
})
export class SessionTabComponent implements OnInit, OnChanges {
  @Input() userId: string = '';
  @Input() appName: string = '';
  @Input() sessionId: string = '';

  @Output() readonly sessionSelected = new EventEmitter<Session>();
  @Output() readonly sessionReloaded = new EventEmitter<Session>();
  @Output() readonly sessionsLoaded = new EventEmitter<Session[]>();

  sessionList: Session[] = [];

  private refreshSessionsSubject = new Subject<void>();

  constructor(
    private sessionService: SessionService,
  ) {
    this.refreshSessionsSubject
      .pipe(
        filter(() => !!this.userId && !!this.appName),
        switchMap(() =>
          this.sessionService.listSessions(this.userId, this.appName).pipe(
            catchError(err => {
              console.error(`Failed to list sessions for app ${this.appName}:`, err);
              return of([]);
            })
          )
        )
      )
      .subscribe((response: any[]) => {
        const sortedApiResults = response.sort(
          (a: any, b: any) =>
            Number(b.last_update_time) - Number(a.last_update_time)
        );
        this.sessionList = sortedApiResults.map(item => this.fromApiResultToSession(item));
        this.sessionsLoaded.emit(this.sessionList);
      });
  }

  ngOnInit(): void {
    if (this.userId && this.appName) {
      this.refreshSessionsSubject.next();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['userId'] || changes['appName']) {
      if (this.userId && this.appName) {
        this.refreshSessionsSubject.next();
      }
    }
  }

  public handleSessionClick(session: { id?: string }): void {
  if (session && typeof session.id === 'string' && session.id.trim() !== '') {
    this.getSession(session.id);
  } else {
    console.warn('Session click ignored: ID is missing or invalid.', session);
  }
}

  getSession(sessionId: string) {
    this.sessionService
      .getSession(this.userId, this.appName, sessionId)
      .subscribe((res) => {
        const session = this.fromApiResultToSession(res);
        this.sessionSelected.emit(session);
      });
  }

  protected getDate(session: Session): string {
    let timeStamp = session.last_update_time;

    const date = new Date(timeStamp * 1000);

    return date.toLocaleString();
  }

  private fromApiResultToSession(apiItem: any): Session {
    return {
      id: apiItem?.id ?? '',
      app_name: apiItem?.appName ?? '',
      user_id: apiItem?.userId ?? '',
      state: apiItem?.state ?? [],
      events: apiItem?.events ?? [],
      last_update_time: apiItem?.lastUpdateTime ?? 0,
    };
  }

  reloadSession(sessionId: string) {
    this.sessionService
      .getSession(this.userId, this.appName, sessionId)
      .subscribe((res) => {
        const session = this.fromApiResultToSession(res);
        this.sessionReloaded.emit(session);
      });
  }

  refreshSession(session?: string) {
    this.refreshSessionsSubject.next();
    if (this.sessionList.length <= 1) {
      return undefined;
    } else {
      let index = this.sessionList.findIndex((s) => s.id == session);
      if (index == this.sessionList.length - 1) {
        index = -1;
      }
      return this.sessionList[index + 1];
    }
  }
}
