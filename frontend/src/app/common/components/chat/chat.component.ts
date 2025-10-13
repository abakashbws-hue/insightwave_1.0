import {
  AfterViewChecked,
  AfterViewInit,
  Component,
  ElementRef,
  inject,
  OnDestroy,
  OnInit,
  Renderer2,
  signal,
  ViewChild,
  WritableSignal,
} from '@angular/core';
import { FormControl, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatDialog } from '@angular/material/dialog';
import {
  MatPaginatorIntl,
  MatPaginatorModule,
} from '@angular/material/paginator';
import { MatSidenav, MatSidenavModule } from '@angular/material/sidenav';
import { MatChipsModule } from '@angular/material/chips';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { fadeInFromLeftAnimation, fadeInOutAnimation, messageAnimation, slideInOutAnimation, slideUpDownAnimation  } from '../../utils/animations';
import {
  catchError,
  distinctUntilChanged,
  filter,
  map,
  Observable,
  of,
  shareReplay,
  switchMap,
  take,
  tap,
} from 'rxjs';

import { HttpErrorResponse } from '@angular/common/http';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ActivatedRoute, NavigationEnd, Router } from '@angular/router';
import { URLUtil } from '../../utils/url-util';
import { AgentRunRequest } from '../../models/AgentRunRequest';
import { Session } from '../../models/Session';
import { AgentService } from '../../services/agent.service';
import { EventService } from '../../services/event.service';
import { SessionService } from '../../services/session.service';
import { PendingEventDialogComponent } from '../pending-event-dialog/pending-event-dialog.component';
import {
  DeleteSessionDialogComponent,
  DeleteSessionDialogData,
} from '../session-tab/delete-session-dialog/delete-session-dialog.component';
import { SessionTabComponent } from '../session-tab/session-tab.component';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { AsyncPipe, CommonModule } from '@angular/common';
import { MatTabsModule } from '@angular/material/tabs';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatDividerModule } from '@angular/material/divider';
import { MatCardModule } from '@angular/material/card';
import { MarkdownModule } from 'ngx-markdown';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { TypingLoaderComponent } from '../typing-loader/typing-loader.component';
import { AuthService } from '../../services/auth.service';
import { ROOT_AGENT_NAME } from '../../utils/constants';
import { QuickStartComponent, ToolCard } from '../quick-start/quick-start.component';


function fixBase64String(base64: string): string {
  // Replace URL-safe characters if they exist
  base64 = base64.replace(/-/g, '+').replace(/_/g, '/');

  // Add missing padding to ensure length is a multiple of 4
  while (base64.length % 4 !== 0) {
    base64 += '=';
  }

  return base64;
}

class CustomPaginatorIntl extends MatPaginatorIntl {
  override nextPageLabel = 'Next Event';
  override previousPageLabel = 'Previous Event';
  override firstPageLabel = 'First Event';
  override lastPageLabel = 'Last Event';

  override getRangeLabel = (page: number, pageSize: number, length: number) => {
    if (length === 0) {
      return `Event 0 of ${length}`; // Handle the case with no items
    }

    length = Math.max(length, 0);
    const startIndex = page * pageSize;

    return `Event ${startIndex + 1} of ${length}`;
  };
}

@Component({
  selector: 'app-chat',
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.scss',
  standalone: true,
  animations: [
    fadeInFromLeftAnimation,
    fadeInOutAnimation,
    slideUpDownAnimation,
    slideInOutAnimation,
    messageAnimation,
  ],
  providers: [{ provide: MatPaginatorIntl, useClass: CustomPaginatorIntl }],
  imports: [
    MatChipsModule,
    MatSidenavModule,
    SessionTabComponent,
    MatIconModule,
    MatSelectModule,
    MatFormFieldModule,
    ReactiveFormsModule,
    AsyncPipe,
    MatTabsModule,
    MatPaginatorModule,
    CommonModule,
    MatSlideToggleModule,
    MatDividerModule,
    MatCardModule,
    FormsModule,
    MarkdownModule,
    MatInputModule,
    MatButtonModule,
    TypingLoaderComponent,
    QuickStartComponent,
  ],
})
export class ChatComponent
  implements OnInit, AfterViewInit, OnDestroy, AfterViewChecked
{
  @ViewChild('videoContainer', { read: ElementRef })
  videoContainer!: ElementRef;
  @ViewChild('sidenav') sidenav!: MatSidenav;
  // @ViewChild(EventTabComponent) eventTabComponent!: EventTabComponent;
  @ViewChild(SessionTabComponent) sessionTab!: SessionTabComponent;
  // @ViewChild(EvalTabComponent) evalTab!: EvalTabComponent;
  @ViewChild('autoScroll') private scrollContainer!: ElementRef;
  @ViewChild('chatInputArea') chatInputArea!: ElementRef<HTMLTextAreaElement>;
  private _nameContainerRef!: ElementRef<HTMLDivElement>;
  @ViewChild('nameContainer')
  set nameContainerRef(ref: ElementRef<HTMLDivElement> | undefined) {
    if (ref) {
      this._nameContainerRef = ref;
      if (this.sessionId && this._nameContainerRef.nativeElement) {
        this.applyRandomNameContainerInternal(false);
      }
    } else {
      console.log('nameContainerRef setter: Ref is undefined.');
    }
  }

  nameContainerVariants = [
    'name-container--variant-1',
    'name-container--variant-2',
    'name-container--variant-3',
  ];
  currentNameContainerVariant: string =
    this.nameContainerVariants[
      Math.floor(Math.random() * this.nameContainerVariants.length)
    ];

  private _snackBar = inject(MatSnackBar);
  enableSseIndicator = signal(false);
  videoElement!: HTMLVideoElement;
  currentMessage = '';
  messages: any[] = [];
  lastTextChunk: string = '';
  streamingTextMessage: any | null = null;
  artifacts: any[] = [];
  userInput: string = '';
  userId = 'user';
  userDisplayName = 'User';
  appName = '';
  sessionId = ``;
  isAudioRecording = false;
  isVideoRecording = false;
  longRunningEvents: any[] = [];
  functionCallEventId = '';
  redirectUri = URLUtil.getBaseUrlWithoutPath();
  showSidePanel = true;
  useSse = false;
  currentSessionState = {};

  eventData = new Map<string, any>();
  eventMessageIndexArray: any[] = [];
  renderedEventGraph: SafeHtml | undefined;

  selectedEvent: any = undefined;
  selectedEventIndex: any = undefined;
  llmRequest: any = undefined;
  llmResponse: any = undefined;
  llmRequestKey = 'gcp.vertex.agent.llm_request';
  llmResponseKey = 'gcp.vertex.agent.llm_response';

  selectedFiles: { file: File; url: string }[] = [];
  private previousMessageCount = 0;

  // Sync query params with value from agent picker.
  private readonly router = inject(Router);
  private readonly activatedRoute = inject(ActivatedRoute);
  protected readonly selectedAppControl = new FormControl<string>('', {
    nonNullable: true,
  });

  private readonly authService = inject(AuthService);

  // Load apps
  private readonly agentService = inject(AgentService);
  protected isLoadingApps: WritableSignal<boolean> = signal(false);
  protected loadingError: WritableSignal<string> = signal('');
  protected readonly apps$: Observable<string[] | undefined> = of([]).pipe(
    tap(() => {
      this.isLoadingApps.set(true);
      this.selectedAppControl.disable();
    }),
    switchMap(() =>
      this.authService.getLoggedInUser().pipe(
        map((user) => {
          this.userId = user?.uid || '';
          this.userDisplayName = user?.displayName || 'User';
        })
      )
    ),
    switchMap(() =>
      this.agentService.listApps().pipe(
        catchError((err: HttpErrorResponse) => {
          this.loadingError.set(err.message);
          return of(undefined);
        })
      )
    ),
    take(1),
    tap((apps) => {
      this.isLoadingApps.set(false);
      this.selectedAppControl.enable();

      // this.router.navigate([], {
      //   relativeTo: this.route,
      //   queryParams: { app: app[0] },
      // });

      this.selectedAppControl.setValue(ROOT_AGENT_NAME);
    }),
    shareReplay()
  );

  isTyping = false;

  quickStartTools: ToolCard[] = [
    {
      id: 'waveplanning_agent',
      title: 'Plan your migration waves',
      description: 'Generate migration waves for a given discovery reports(RV tools, mcdc, txture etc.).',
      icon: 'translate',
      utterances: [
        'Generate the migration wave plan.',
      ]
    },
    {
      id: 'mig_pattern_doc',
      title: 'Migration Patterns',
      description: 'Generate migration pattern templates for given landing zone.',
      icon: 'analytics',
      utterances: [
        'Generate migration planning doc to migrate from on-prem(VMWare) to GCVE.',
        'Generate migration planning doc to migrate from on-prem(VMWare) to GKE.',
        'Generate migration planning doc to migrate from on-prem(VMWare) to GCE.',
      ]
    },
    {
      id: 'runbook_agent',
      title: 'Runbooks',
      description: 'Generate step by step migration runbook for given migration pattern',
      icon: 'insights',
      utterances: [
        'Generate migration runbook template to migrate from on-prem(VMWare) to GCVE.',
        'Generate migration runbook template to migrate from on-prem(VMWare) to GKE.',
        'Generate migration runbook template to migrate from on-prem(VMWare) to GCE.',
      ]
    }
  ];

  constructor(
    private sanitizer: DomSanitizer,
    // private artifactService: ArtifactService,
    // private audioService: AudioService,
    // private webSocketService: WebSocketService,
    // private videoService: VideoService,
    private dialog: MatDialog,
    private eventService: EventService,
    private sessionService: SessionService,
    private route: ActivatedRoute,
    private renderer: Renderer2
  ) {}

  get userFirstName(): string {
    return this.userDisplayName ? this.userDisplayName.split(' ')[0] : '';
  }

  ngOnInit(): void {
    this.syncSelectedAppFromUrl();
    this.updateSelectedAppUrl();

    // this.webSocketService.onCloseReason().subscribe((closeReason) => {
    //   const error =
    //     'Please check server log for full details: \n' + closeReason;
    //   this.openSnackBar(error, 'OK');
    // });

    // OAuth HACK: Opens oauth poup in a new window. If the oauth callback
    // is successful, the new window acquires the auth token, state and
    // optionally the scope. Send this back to the main window.
    const location = new URL(window.location.href);
    const searchParams = location.searchParams;
    if (searchParams.has('code')) {
      const authResponseUrl = window.location.href;
      // Send token to the main window
      window.opener?.postMessage({ authResponseUrl }, window.origin);
      // Close the popup
      window.close();
    }

    this.agentService.getApp().subscribe((app) => {
      this.appName = app;
    });
  }

  ngAfterViewInit() {
    this.showSidePanel = true;
    this.sidenav.open();
  }

  ngAfterViewChecked() {
    // Defer scrolling to ensure the DOM has fully rendered and animations have settled.
    // This helps in getting the correct scrollHeight.
    if (
      this.scrollContainer?.nativeElement &&
      this.messages.length !== this.previousMessageCount
    ) {
      // Update the message count immediately to prevent multiple scroll attempts for the same state.
      this.previousMessageCount = this.messages.length;
      setTimeout(() => {
        this.scrollContainer.nativeElement.scrollTop =
          this.scrollContainer.nativeElement.scrollHeight;
      }, 0);
    }
  }

  selectApp(appName: string) {
    if (appName !== this.appName) {
      this.agentService.setApp(appName);
      this.createSession();
      this.eventData = new Map<string, any>();
      this.eventMessageIndexArray = [];
      this.messages = [];
      this.artifacts = [];
      this.userInput = '';
      this.longRunningEvents = [];
    }
  }

  createSession() {
    this.sessionService
      .createSession(this.userId, this.appName)
      .subscribe((res) => {
        this.currentSessionState = res.state;
        this.sessionId = res.id;
        this.applyRandomNameContainer();
        this.sessionTab.refreshSession();
        this.userInput = '';
      });
  }

  async sendMessage(event: Event) {
    event.preventDefault();

    const textInput = this.userInput.trim();
    const filesToUpload = [...this.selectedFiles];

    if (!textInput && filesToUpload.length === 0) {
      return;
    }

    const displayMessage: { role: string; text?: string; attachments?: any[] } =
      { role: 'user' };
    if (textInput) {
      displayMessage.text = textInput;
    }
    if (filesToUpload.length > 0) {
      displayMessage.attachments = filesToUpload.map((file) => ({
        file: file.file,
        url: file.url,
      }));
    }
    this.messages.push(displayMessage);

    const userMessageParts = await this.getUserMessageParts();

    const req: AgentRunRequest = {
      app_name: this.appName,
      user_id: this.userId,
      session_id: this.sessionId,
      new_message: {
        role: 'user',
        parts: userMessageParts,
      },
      streaming: this.useSse,
    };

    this.userInput = '';
    this.selectedFiles = [];
    // If you have a reference to the HTML file input element and want to clear it:
    // e.g., @ViewChild('fileHtmlInput') fileHtmlInputRef: ElementRef<HTMLInputElement>;
    // if (this.fileHtmlInputRef && this.fileHtmlInputRef.nativeElement) {
    //   this.fileHtmlInputRef.nativeElement.value = '';
    // }

    // Reset textarea height after input is cleared and DOM updates
    setTimeout(() => {
      if (this.chatInputArea && this.chatInputArea.nativeElement) {
        this.adjustTextareaHeight(this.chatInputArea.nativeElement);
      }
    });

    let index = this.eventMessageIndexArray.length - 1;
    this.streamingTextMessage = null;
    this.isTyping = false;

    this.agentService.run_sse(req).subscribe({
      next: async (chunk) => {
        const chunkJson = JSON.parse(chunk);
        if (chunkJson.error) {
          this.openSnackBar(chunkJson.error, 'OK');
          this.isTyping = true;
          return;
        }
        if (chunkJson.content) {
          for (let part of chunkJson.content.parts) {
            index += 1;
            this.processPart(chunkJson, part, index);
          }
        }
        this.isTyping = true;
      },
      error: (err) => {
        console.error('SSE error:', err);
        this.isTyping = false;
        this.openSnackBar('Error sending message. Please try again.', 'OK');
      },
      complete: () => {
        this.streamingTextMessage = null;
        this.sessionTab?.reloadSession(this.sessionId);
        this.isTyping = false;
      },
    });
  }

  private processPart(chunkJson: any, part: any, index: number) {
    if (part.text) {
      const newChunk = part.text;
      if (!this.streamingTextMessage) {
        this.streamingTextMessage = {
          role: 'bot',
          text: this.processThoughtText(newChunk),
          thought: part.thought ? true : false,
        };

        if (
          chunkJson.grounding_metadata &&
          chunkJson.grounding_metadata.searchEntryPoint &&
          chunkJson.grounding_metadata.searchEntryPoint.renderedContent
        ) {
          this.streamingTextMessage.renderedContent =
            chunkJson.grounding_metadata.searchEntryPoint.renderedContent;
        }

        this.messages.push(this.streamingTextMessage);
        if (!this.useSse) {
          this.storeEvents(part, chunkJson, index);
          this.eventMessageIndexArray[index] = newChunk;
          this.streamingTextMessage = null;
          return;
        }
      } else {
        if (newChunk == this.streamingTextMessage.text) {
          this.storeEvents(part, chunkJson, index);
          this.eventMessageIndexArray[index] = newChunk;
          this.streamingTextMessage = null;
          return;
        }
        this.streamingTextMessage.text += newChunk;
      }
    } else {
      this.storeEvents(part, chunkJson, index);
      this.storeMessage(part, chunkJson, index, false);
    }
  }

  async getUserMessageParts() {
    let parts: any = [{ text: `${this.userInput}` }];
    if (this.selectedFiles.length > 0) {
      for (const file of this.selectedFiles) {
        parts.push({
          inline_data: {
            data: await this.readFileAsBytes(file.file),
            mime_type: file.file.type,
          },
        });
      }
    }
    return parts;
  }

  readFileAsBytes(file: File): Promise<ArrayBuffer> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e: any) => {
        const base64Data = e.target.result.split(',')[1];
        resolve(base64Data);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file); // Read as raw bytes
    });
  }

  private updateRedirectUri(urlString: string, newRedirectUri: string): string {
    try {
      const url = new URL(urlString);
      const searchParams = url.searchParams;
      searchParams.set('redirect_uri', newRedirectUri);
      return url.toString();
    } catch (error) {
      console.warn('Failed to update redirect URI: ', error);
      return urlString;
    }
  }

  private storeMessage(part: any, e: any, index: number, isReplay = false) {
    if (!isReplay && e.longRunningToolIds && e.longRunningToolIds.length > 0) {
      this.getAsyncFunctionsFromParts(e.longRunningToolIds, e.content.parts);
      const func = this.longRunningEvents[0];
      if (
        func.args.authConfig &&
        func.args.authConfig.exchangedAuthCredential &&
        func.args.authConfig.exchangedAuthCredential.oauth2
      ) {
        // for OAuth
        const authUri =
          func.args.authConfig.exchangedAuthCredential.oauth2.authUri;
        const updatedAuthUri = this.updateRedirectUri(
          authUri,
          this.redirectUri
        );
        this.openOAuthPopup(updatedAuthUri)
          .then((authResponseUrl) => {
            this.functionCallEventId = e.id;
            this.sendOAuthResponse(func, authResponseUrl, this.redirectUri);
          })
          .catch((error) => {
            console.error('OAuth Error:', error);
          });
      } else {
        this.functionCallEventId = e.id;
      }
    }
    if (part.text) {
      let message: any = {
        role: e.author === 'user' ? 'user' : 'bot',
        text: part.text,
      };
      if (
        e.grounding_metadata &&
        e.grounding_metadata.searchEntryPoint &&
        e.grounding_metadata.searchEntryPoint.renderedContent
      ) {
        message.renderedContent =
          e.grounding_metadata.searchEntryPoint.renderedContent;
      }
      this.messages.push(message);
      this.eventMessageIndexArray[index] = part.text;
    } else if (part.functionCall) {
      this.messages.push({
        role: e.author === 'user' ? 'user' : 'bot',
        functionCall: part.functionCall,
      });
      this.eventMessageIndexArray[index] = part.functionCall;
    } else if (part.functionResponse) {
      this.messages.push({
        role: e.author === 'user' ? 'user' : 'bot',
        functionResponse: part.functionResponse,
      });

      if (e.actions && e.actions.artifact_delta) {
        for (const key in e.actions.artifact_delta) {
          if (e.actions.artifact_delta.hasOwnProperty(key)) {
            // this.renderArtifact(key, e.actions.artifact_delta[key]);
          }
        }
      }

      this.eventMessageIndexArray[index] = part.functionResponse;
    } else if (part.executableCode) {
      this.messages.push({
        role: e.author === 'user' ? 'user' : 'bot',
        executableCode: part.executableCode,
      });
      this.eventMessageIndexArray[index] = part.executableCode;
    } else if (part.codeExecutionResult) {
      this.messages.push({
        role: e.author === 'user' ? 'user' : 'bot',
        codeExecutionResult: part.codeExecutionResult,
      });
      this.eventMessageIndexArray[index] = part.codeExecutionResult;
      if (e.actions && e.actions.artifact_delta) {
        for (const key in e.actions.artifact_delta) {
          if (e.actions.artifact_delta.hasOwnProperty(key)) {
            // this.renderArtifact(key, e.actions.artifact_delta[key]);
          }
        }
      }
    }
  }

  // private renderArtifact(artifactId: string, versionId: string) {
  //   // Add a placeholder message for the artifact
  //   // Feed the placeholder with the artifact data after it's fetched
  //   this.messages.push({
  //     role: 'bot',
  //     inline_data: {
  //       data: '',
  //       mime_type: 'image/png',
  //     },
  //   });

  //   const currentIndex = this.messages.length - 1;

  //   this.artifactService
  //     .getArtifactVersion(
  //       this.userId,
  //       this.appName,
  //       this.sessionId,
  //       artifactId,
  //       versionId,
  //     )
  //     .subscribe((res) => {
  //       const mimeType = res.inlineData.mimeType;

  //       const fixedBase64Data = fixBase64String(res.inlineData.data);

  //       const base64Data = `data:${mimeType};base64,${fixedBase64Data}`;

  //       this.messages[currentIndex] = {
  //         role: 'bot',
  //         inline_data: {
  //           data: base64Data,
  //           mime_type: mimeType,
  //         },
  //       };

  //       // To trigger ngOnChanges in the artifact tab component
  //       this.artifacts = [
  //         ...this.artifacts,
  //         {
  //           id: artifactId,
  //           data: base64Data,
  //           mimeType,
  //           versionId,
  //         },
  //       ];
  //     });
  // }

  private storeEvents(part: any, e: any, index: number) {
    let key = e.content.role + ':';
    if (part.text) {
      key += index + part.text;
    } else if (part.functionCall) {
      key += 'functionCall:' + index + ':' + part.functionCall.name;
    } else if (part.functionResponse) {
      key += 'functionResponse:' + index + ':' + part.functionResponse.name;
    } else if (part.executableCode) {
      key +=
        'executableCode:' + index + ':' + part.executableCode.code.slice(0, 10);
    } else if (part.codeExecutionResult) {
      key +=
        'codeExecutionResult:' + index + ':' + part.codeExecutionResult.outcome;
    }
    this.eventData.set(key, e);
    this.eventData = new Map(this.eventData);
  }

  private sendOAuthResponse(
    func: any,
    authResponseUrl: string,
    redirect_uri: string
  ) {
    this.longRunningEvents.pop();
    const authResponse: AgentRunRequest = {
      app_name: this.appName,
      user_id: this.userId,
      session_id: this.sessionId,
      new_message: {
        role: 'user',
        parts: [],
      },
    };

    var authConfig = structuredClone(func.args.authConfig);
    authConfig.exchangedAuthCredential.oauth2.authResponseUri = authResponseUrl;
    authConfig.exchangedAuthCredential.oauth2.redirectUri = redirect_uri;

    authResponse.function_call_event_id = this.functionCallEventId;
    authResponse.new_message.parts.push({
      function_response: {
        id: func.id,
        name: func.name,
        response: authConfig,
      },
    });
    this.isTyping = false;
    this.agentService.run(authResponse).subscribe((res) => {
      let index = this.eventMessageIndexArray.length - 1;
      for (const e of res) {
        if (e.content) {
          for (let part of e.content.parts) {
            index += 1;
            this.processPart(e, part, index);
          }
        }
      }
      this.isTyping = false;
    });
  }

  openDialog(): void {
    const dialogRef = this.dialog.open(PendingEventDialogComponent, {
      width: '600px',
      data: {
        event: this.longRunningEvents[0],
        app_name: this.appName,
        user_id: this.userId,
        session_id: this.sessionId,
        function_call_event_id: this.functionCallEventId,
      },
    });

    dialogRef.afterClosed().subscribe((t) => {
      if (t) {
        this.longRunningEvents = t.events;
        this.messages.push({
          role: 'bot',
          text: t.text,
        });
      }
    });
  }

  clickEvent(i: number) {
    // const entry = Array.from(this.eventData.entries())[
    //   i - this.userMessagesLength(i)
    // ];
    // const [key, value] = entry;
    // this.sidenav.open();
    // this.showSidePanel = true;
    // this.selectedEvent = value;
    // this.selectedEventIndex = this.getIndexOfKeyInMap(key);
    // this.eventService.getEventTrace(this.selectedEvent.id).subscribe((res) => {
    //   this.llmRequest = JSON.parse(res[this.llmRequestKey]);
    //   this.llmResponse = JSON.parse(res[this.llmResponseKey]);
    // });
    // this.eventService
    //   .getEvent(
    //     this.userId,
    //     this.appName,
    //     this.sessionId,
    //     this.selectedEvent.id
    //   )
    //   .subscribe(async (res) => {
    //     if (!res.dot_src) {
    //       this.renderedEventGraph = undefined;
    //       return;
    //     }
    //     const graph_src = res.dot_src;
    //     const viz = await instance();
    //     const svg = viz.renderString(graph_src, {
    //       format: 'svg',
    //       engine: 'dot',
    //     });
    //     this.renderedEventGraph = this.sanitizer.bypassSecurityTrustHtml(svg);
    //   });
  }

  userMessagesLength(i: number) {
    return this.messages.slice(0, i).filter((m) => m.role == 'user').length;
  }

  ngOnDestroy(): void {
    // this.webSocketService.closeConnection();
  }

  toggleAudioRecording() {
    this.isAudioRecording
      ? this.stopAudioRecording()
      : this.startAudioRecording();
    this.isAudioRecording = !this.isAudioRecording;
  }

  startAudioRecording() {
    // const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    // this.webSocketService.connect(
    //   `${protocol}://${URLUtil.getWSServerUrl()}/run_live?app_name=${this.appName}&user_id=${this.userId}&session_id=${this.sessionId}`,
    // );
    // this.audioService.startRecording();
    // this.messages.push({role: 'user', text: 'Speaking...'});
    // this.messages.push({role: 'bot', text: 'Speaking...'});
  }

  stopAudioRecording() {
    // this.audioService.stopRecording();
    // this.webSocketService.closeConnection();
  }

  toggleVideoRecording() {
    this.isVideoRecording
      ? this.stopVideoRecording()
      : this.startVideoRecording();
    this.isVideoRecording = !this.isVideoRecording;
  }

  startVideoRecording() {
    // const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    // this.webSocketService.connect(
    //   `${protocol}://${URLUtil.getWSServerUrl()}/run_live?app_name=${this.appName}&user_id=${this.userId}&session_id=${this.sessionId}`,
    // );
    // this.videoService.startRecording(this.videoContainer);
    // this.audioService.startRecording();
    // this.messages.push({role: 'user', text: 'Speaking...'});
  }

  stopVideoRecording() {
    // this.audioService.stopRecording();
    // this.videoService.stopRecording(this.videoContainer);
    // this.webSocketService.closeConnection();
  }

  private getAsyncFunctionsFromParts(pendingIds: any[], parts: any[]) {
    for (const part of parts) {
      if (part.functionCall && pendingIds.includes(part.functionCall.id)) {
        this.longRunningEvents.push(part.functionCall);
      }
    }
  }

  private openOAuthPopup(url: string): Promise<any> {
    return new Promise((resolve, reject) => {
      // Open OAuth popup
      const popup = window.open(url, 'oauthPopup', 'width=600,height=700');

      if (!popup) {
        reject('Popup blocked!');
        return;
      }

      // Listen for messages from the popup
      window.addEventListener(
        'message',
        (event) => {
          if (event.origin !== window.location.origin) {
            return; // Ignore messages from unknown sources
          }
          const { authResponseUrl } = event.data;
          if (authResponseUrl) {
            resolve(authResponseUrl);
          } else {
            reject('OAuth failed');
          }
        },
        { once: true }
      );
    });
  }

  toggleSidePanel() {
    this.showSidePanel = !this.showSidePanel;
  }

  protected updateWithSelectedSession(session: Session) {
    if (!session || !session.id || !session.events || !session.state) {
      console.log('Session is not valid');
      return;
    }

    if (this.sessionId !== session.id) {
      this.applyRandomNameContainer();
    }
    this.sessionId = session.id;
    this.currentSessionState = session.state;

    // reset event and message data
    this.eventData.clear();
    this.eventMessageIndexArray = [];
    this.messages = [];
    this.artifacts = [];
    let index = 0;

    session.events.forEach((event: any) => {
      event.content.parts.forEach((part: any) => {
        this.storeMessage(part, event, index, true);
        index += 1;
        if (event.author && event.author !== 'user') {
          this.storeEvents(part, event, index);
        }
      });
    });
  }

  // Apply a random background variant to the name container
  private applyRandomNameContainer(): void {
    if (this._nameContainerRef && this._nameContainerRef.nativeElement) {
      this.applyRandomNameContainerInternal();
    } else {
      console.warn(
        'applyRandomNameContainerInternal: _nameContainerRef not yet available. Waiting for ViewChild setter or element to render.'
      );
    }
  }

  private applyRandomNameContainerInternal(
    changeNeeded: boolean = true
  ): void {
    if (!this._nameContainerRef || !this._nameContainerRef.nativeElement) {
      console.warn(
        'Internal: _nameContainerRef or its nativeElement is not available. Cannot apply background.'
      );
      return;
    }

    const nameContainerElement = this._nameContainerRef.nativeElement;

    if (this.currentNameContainerVariant) {
      this.renderer.removeClass(
        nameContainerElement,
        this.currentNameContainerVariant
      );
    }

    if (changeNeeded) {
      const randomIndex = Math.floor(
        Math.random() * this.nameContainerVariants.length
      );
      this.currentNameContainerVariant =
        this.nameContainerVariants[randomIndex];
    }
    this.renderer.addClass(
      nameContainerElement,
      this.currentNameContainerVariant
    );

    nameContainerElement.style.animation = 'none';
    nameContainerElement.offsetHeight;
    nameContainerElement.style.animation = '';
  }

  protected updateSessionState(session: Session) {
    this.currentSessionState = session.state;
  }

  onNewSessionClick() {
    if (this.sessionId && this.messages.length === 0) {
      this.userInput = '';
    } else {
      this.createSession();
    }
    this.eventData.clear();
    this.eventMessageIndexArray = [];
    this.messages = [];
    this.artifacts = [];
    this.longRunningEvents = [];
  }

  onFileSelect(event: Event) {
    const input = event.target as HTMLInputElement;
    if (input.files) {
      for (let i = 0; i < input.files.length; i++) {
        const file = input.files[i];
        const url = URL.createObjectURL(file);
        this.selectedFiles.push({ file, url });
      }
    }
    input.value = '';
  }

  removeFile(index: number) {
    URL.revokeObjectURL(this.selectedFiles[index].url);
    this.selectedFiles.splice(index, 1);
  }

  toggleSse() {
    this.useSse = !this.useSse;
  }

  selectEvent(key: string) {
    this.selectedEvent = this.eventData.get(key);
    this.selectedEventIndex = this.getIndexOfKeyInMap(key);
    this.eventService.getEventTrace(this.selectedEvent.id).subscribe((res) => {
      this.llmRequest = JSON.parse(res[this.llmRequestKey]);
      this.llmResponse = JSON.parse(res[this.llmResponseKey]);
    });
    this.eventService
      .getEvent(
        this.userId,
        this.appName,
        this.sessionId,
        this.selectedEvent.id
      )
      .subscribe(async (res) => {
        if (!res.dot_src) {
          this.renderedEventGraph = undefined;
          return;
        }
        const graph_src = res.dot_src;
        // const viz = await instance();
        // const svg = viz.renderString(graph_src, {
        //   format: 'svg',
        //   engine: 'dot',
        // });
        // this.renderedEventGraph = this.sanitizer.bypassSecurityTrustHtml(svg);
      });
  }

  protected deleteSession(session: string) {
    const dialogData: DeleteSessionDialogData = {
      title: 'Confirm delete',
      message: `Are you sure you want to delete this session ${this.sessionId}?`,
      confirmButtonText: 'Delete',
      cancelButtonText: 'Cancel',
    };

    const dialogRef = this.dialog.open(DeleteSessionDialogComponent, {
      width: '600px',
      data: dialogData,
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (result) {
        this.sessionService
          .deleteSession(this.userId, this.appName, session)
          .subscribe((res) => {
            const nextSession = this.sessionTab.refreshSession(session);
            if (nextSession && nextSession.id) {
              this.sessionTab.getSession(nextSession.id);
            } else {
              window.location.reload();
            }
          });
      } else {
      }
    });
  }

  private syncSelectedAppFromUrl() {
    this.router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        map(() => this.activatedRoute.snapshot.queryParams)
      )
      .subscribe((params) => {
        const app = params['app'];
        if (app) {
          this.selectedAppControl.setValue(app);
        }
      });
  }

  private updateSelectedAppUrl() {
    this.selectedAppControl.valueChanges
      .pipe(distinctUntilChanged(), filter(Boolean))
      .subscribe((app: string) => {
        this.selectApp(app);

        // Disable navigation as we only have one app
        // // Navigate if selected app changed.
        // const selectedAgent = this.activatedRoute.snapshot.queryParams['app'];
        // if (app === selectedAgent) {
        //   return;
        // }
        // this.router.navigate([], {
        //   queryParams: { app: app },
        //   queryParamsHandling: 'merge',
        // });
      });
  }

  handlePageEvent(event: any) {
    if (event.pageIndex >= 0) {
      const key = this.getKeyAtIndexInMap(event.pageIndex);
      if (key) {
        this.selectEvent(key);
      }
    }
  }

  closeSelectedEvent() {
    this.selectedEvent = undefined;
    this.selectedEventIndex = undefined;
  }

  private getIndexOfKeyInMap(key: string): number | undefined {
    let index = 0;
    const mapOrderPreservingSort = (a: any, b: any): number => 0; // Simple compare function

    const sortedKeys = Array.from(this.eventData.keys()).sort(
      mapOrderPreservingSort
    );

    for (const k of sortedKeys) {
      if (k === key) {
        return index;
      }
      index++;
    }
    return undefined; // Key not found
  }

  private getKeyAtIndexInMap(index: number): string | undefined {
    const mapOrderPreservingSort = (a: any, b: any): number => 0; // Simple compare function

    const sortedKeys = Array.from(this.eventData.keys()).sort(
      mapOrderPreservingSort
    );

    if (index >= 0 && index < sortedKeys.length) {
      return sortedKeys[index];
    }
    return undefined; // Index out of bounds
  }

  openSnackBar(message: string, action: string) {
    this._snackBar.open(message, action);
  }

  private processThoughtText(text: string) {
    return text.replace('/*PLANNING*/', '').replace('/*ACTION*/', '');
  }

  openLink(url: string) {
    window.open(url, '_blank');
  }

  renderGooglerSearch(content: string) {
    return this.sanitizer.bypassSecurityTrustHtml(content);
  }

  // Adjust the height of the textarea based on its content
  adjustTextareaHeight(textarea: HTMLTextAreaElement): void {
    textarea.style.height = 'auto'; // Reset height to recalculate based on content
    textarea.style.height = `${textarea.scrollHeight}px`; // Set height to scroll height

    // Maximum height to prevent the textarea from growing indefinitely
    const maxHeight = 200;
    if (textarea.scrollHeight > maxHeight) {
      textarea.style.height = `${maxHeight}px`;
      textarea.style.overflowY = 'auto';
    } else {
      textarea.style.overflowY = 'hidden';
    }
  }

  onUtteranceSelected(utterance: string) {
    // Add a small delay to allow the animation to complete
    setTimeout(() => {
      this.userInput = utterance;

      if (utterance.includes('{') && utterance.includes('}')) {
        if (this.chatInputArea && this.chatInputArea.nativeElement) {
          this.chatInputArea.nativeElement.focus();
          this.adjustTextareaHeight(this.chatInputArea.nativeElement);
        }
      } else {
        this.sendMessage(new Event('submit'));
      }
    }, 100);
  }
}
