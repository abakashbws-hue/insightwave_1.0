import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-spinner',
  templateUrl: './spinner.component.html',
  styleUrl: './spinner.component.scss',
  standalone: true,
})
export class SpinnerComponent {
  @Input() message: string = 'Processing...';
  @Input() isOpaque: boolean = false;
}
