import { MatDialog } from '@angular/material/dialog';
import { MarkedOptions, MarkedRenderer } from 'ngx-markdown';
import { Observable } from 'rxjs';
import { ExitDialogComponent } from '../components/exit-dialog/exit-dialog.component';

// Function that returns `MarkedOptions` with renderer override
export function markedOptionsFactory(): MarkedOptions {
  const renderer = new MarkedRenderer();
  const linkRenderer = renderer.link;
  renderer.link = (href, title, text) => {
    const html = linkRenderer.call(renderer, href, title, text);
    return html.replace(/^<a /, '<a target="_blank" ');
  };

  return {
    renderer: renderer,
    gfm: true,
    breaks: false,
    pedantic: false,
  };
}

// Helper method to show exit dialog
export function showExitDialog(dialog: MatDialog): Observable<boolean> {
  return dialog
    .open(ExitDialogComponent, {
      width: '350px',
      disableClose: true,
    })
    .afterClosed();
}
