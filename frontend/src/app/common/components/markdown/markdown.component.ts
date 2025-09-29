import { Component, Input, OnChanges, SimpleChanges, TemplateRef, ViewChild, inject } from '@angular/core';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { Clipboard } from '@angular/cdk/clipboard';
import { MarkdownComponent as NgxMarkdownComponent } from 'ngx-markdown';

// Firebase imports
import { ref, getDownloadURL, Storage } from '@angular/fire/storage';
import { NgIf, NgTemplateOutlet } from '@angular/common';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';

@Component({
  selector: 'app-markdown',
  templateUrl: './markdown.component.html',
  styleUrls: ['./markdown.component.scss'],
  standalone: true,
  imports: [
    NgxMarkdownComponent,
    NgIf,
    NgTemplateOutlet,
    MatProgressSpinnerModule,
    MatIconModule,
    MatButtonModule,
    MatSnackBarModule,
  ],
})
export class MarkdownComponent implements OnChanges {
  @Input() src?: string; // Path in Firebase Storage (e.g., 'user-guide-markdowns/user-guide.md')
  @Input() dynamicData: Record<string, string | undefined> = {}; // Object for placeholder values {{key}}

  @ViewChild(NgxMarkdownComponent) private ngxMarkdown!: NgxMarkdownComponent;

  processedMarkdown: string | undefined;
  isLoading = false;
  error: string | null = null;

  private storage = inject(Storage);
  private snackBar = inject(MatSnackBar);
  private clipboard = inject(Clipboard);

  ngOnChanges(): void {
    if (!this.processedMarkdown && this.src) {
      this.fetchAndProcessMarkdown();
    } else if (!this.src) {
      // If src is removed, clear processed markdown
      this.processedMarkdown = undefined;
      this.isLoading = false;
      this.error = null;
    }
  }

  async fetchAndProcessMarkdown(): Promise<void> {
    if (!this.src) return;

    this.isLoading = true;
    this.error = null;
    this.processedMarkdown = undefined; // Clear previous content

    try {
      const markdownRef = ref(this.storage, this.src);
      const url = await getDownloadURL(markdownRef);
      const response = await fetch(url);

      if (!response.ok) {
        // Throw a more specific error including the status
        const errorText = await response.text().catch(() => 'Could not read error response body'); // Try to get response body
        throw new Error(`HTTP error! Status: ${response.status} ${response.statusText}. Response: ${errorText}`);
      }

      const rawMarkdown = await response.text();
      this.processedMarkdown = this.replacePlaceholders(rawMarkdown);

    } catch (err: any) {
      console.error(`Error fetching markdown from ${this.src}:`, err);
      this.error = `Failed to load guide. ${err.message || 'Please check the console for details.'}`;
      this.processedMarkdown = `*Error loading content from ${this.src}*`; // Show error inline
    } finally {
      this.isLoading = false;
    }
  }

  replacePlaceholders(markdown: string): string {
    let processed = markdown;
    for (const key in this.dynamicData) {
      if (Object.prototype.hasOwnProperty.call(this.dynamicData, key)) {
        const placeholder = `{{${key}}}`;
        // Use RegExp for global replacement, escape special characters in key
        const regex = new RegExp(placeholder.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&'), 'g');
        const value = this.dynamicData[key] ?? placeholder; // Use placeholder itself if value is null/undefined
        processed = processed.replace(regex, value);
      }
    }
    return processed;
  }

  onCopyToClipboard(textToCopy?: string): void {
    const text = textToCopy || this.ngxMarkdown?.element?.nativeElement?.innerText || '';
    if (this.clipboard.copy(text)) {
      this.snackBar.open('Content copied to clipboard!', 'Close', { duration: 3000 });
    } else {
      this.snackBar.open('Failed to copy content.', 'Close', { duration: 3000 });
    }
  }
}
