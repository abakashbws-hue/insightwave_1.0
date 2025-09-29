import { TextFieldModule } from '@angular/cdk/text-field';
import { CommonModule } from '@angular/common';
import { Component, OnInit, Output, EventEmitter, Input } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { fadeIn } from '../../utils/animations';
import { FirestoreDataService } from '../../services/firestore-data.service';
import { firstValueFrom, Observable, of } from 'rxjs';
import { AppUser } from '../../interfaces/user-model.interface';
import { LocalStorageService } from '../../services/local-storage.service';
import { LOGGED_IN_USER_PROFILE } from '../../utils/constants';

export interface FeedbackPayload {
  toolName: string;
  rating: number;
  comments: string;
  userId?: string;
  userDisplayName?: string | null;
  userEmail?: string | null;
  submittedAt: string;
}

export const FEEDBACK_COLLECTION_NAME = 'userFeedback';

interface FeedbackFormValue {
  rating: number;
  comments: string;
}

@Component({
  selector: 'app-feedback-form',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule, 
    MatIconModule, 
    MatInputModule, 
    MatFormFieldModule, 
    MatButtonModule, 
    TextFieldModule,
    MatSnackBarModule,
  ],
  templateUrl: './feedback-form.component.html',
  styleUrl: './feedback-form.component.scss',
  animations: [fadeIn]
})
export class FeedbackFormComponent implements OnInit {
  @Input() toolName: string = '';

  user$: Observable<AppUser | null>;

  feedbackForm: FormGroup;
  readonly maxRating = 5;
  currentRating = 0;
  stars: number[] = [];

  isSubmitted = false;
  errorMessage: string | null = null;

  // Output event to emit the feedback data to the parent component (matches the structure being saved)
  @Output() feedbackSubmit = new EventEmitter<FeedbackPayload>();

  constructor(
    private fb: FormBuilder,
    private firestoreService: FirestoreDataService,
    private localStorageService: LocalStorageService,
    private snackBar: MatSnackBar
  ) {
    this.stars = Array(this.maxRating).fill(0).map((_, i) => i + 1);
    this.feedbackForm = this.fb.group({
      rating: [0, Validators.min(1)], // Rating is required (at least 1 star)
      comments: ['', Validators.maxLength(500)] // Optional comments with max length
    });

    this.user$ = of(this.localStorageService.get<AppUser>(LOGGED_IN_USER_PROFILE));
  }

  ngOnInit(): void {
    // Set initial rating value in the form
    this.feedbackForm.patchValue({ rating: this.currentRating });
  }

  /**
   * Sets the rating when a star is clicked.
   * @param rating The rating value selected.
   */
  rate(rating: number): void {
    this.currentRating = rating;
    this.feedbackForm.patchValue({ rating: this.currentRating });
  }

  /**
   * Handles form submission.
   */
  async onSubmit(): Promise<void> {
    if (this.feedbackForm.valid) {
      this.errorMessage = null; // Clear any previous error message
      const formValue: FeedbackFormValue = this.feedbackForm.value;
      const baseFeedback: Omit<FeedbackPayload, 'userId' | 'userDisplayName' | 'userEmail'> = {
        toolName: this.toolName,
        rating: formValue.rating,
        comments: formValue.comments || '',
        submittedAt: new Date().toISOString(),
      };

      // Emit the event first, so parent component can react immediately
      this.feedbackSubmit.emit(baseFeedback);
      this.isSubmitted = true;
      this.feedbackForm.disable(); // Disable the form after submission

      // Now, try to save to Firestore
      try {
        const appUser: AppUser | null = await firstValueFrom(this.user$);

        if (appUser && appUser.id) {
          const feedbackDocToSave: FeedbackPayload = {
            ...baseFeedback,
            userId: appUser.id,
            userDisplayName: appUser.displayName,
            userEmail: appUser.email,
          };

          await this.firestoreService.addRecord(FEEDBACK_COLLECTION_NAME, feedbackDocToSave);
        } else {
          console.warn('Feedback submitted locally, but user not logged in. Could not save to Firestore.');
          // User not logged in, save only base feedback (userId, etc. will be undefined/missing)
          await this.firestoreService.addRecord(FEEDBACK_COLLECTION_NAME, baseFeedback);
          this.snackBar.open('Feedback submitted. Log in to save feedback with your profile.', 'Close', { duration: 5000 });
        }
      } catch (error) { // Submission was not fully successful
        console.error('Error saving feedback to Firestore:', error);
        this.isSubmitted = false; 
        this.errorMessage = 'We encountered an issue submitting your feedback. Please try again.';
        
        // The form remains disabled as per original logic.
        // Consider if re-enabling or providing a retry mechanism is needed for critical feedback.
      }
    } else {
      console.log('Form is invalid');
      // Mark fields as touched to show errors
      this.feedbackForm.markAllAsTouched();
    }
  }

  resetForm(): void {
    this.feedbackForm.reset({ rating: 0, comments: '' });
    this.currentRating = 0;
    this.isSubmitted = false;
    this.errorMessage = null;
    this.feedbackForm.enable();
  }
}
