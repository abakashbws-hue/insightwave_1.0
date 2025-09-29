import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import {
  trigger,
  state,
  style,
  transition,
  animate,
} from '@angular/animations';

export interface ToolCard {
  id: string;
  title: string;
  description: string;
  icon: string;
  utterances: string[];
}

@Component({
  selector: 'app-quick-start',
  templateUrl: './quick-start.component.html',
  styleUrls: ['./quick-start.component.scss'],
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatButtonModule,
  ],
  animations: [
    trigger('expandCollapse', [
      state(
        'collapsed',
        style({
          height: '0',
          opacity: '0',
          overflow: 'hidden',
        })
      ),
      state(
        'expanded',
        style({
          height: '*',
          opacity: '1',
        })
      ),
      transition('collapsed => expanded', [animate('500ms ease-in-out')]),
      transition('expanded => collapsed', [animate('0ms')]),
    ]),
  ],
})
export class QuickStartComponent {
  @Input() tools: ToolCard[] = [];
  @Output() utteranceSelected = new EventEmitter<string>();

  expandedCardId: string | null = null;

  toggleCard(cardId: string) {
    this.expandedCardId = this.expandedCardId === cardId ? null : cardId;
  }

  onUtteranceClick(utterance: string) {
    this.utteranceSelected.emit(utterance);
  }
}
