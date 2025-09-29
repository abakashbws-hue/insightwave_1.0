import { NgIf } from '@angular/common';
import { Component, EventEmitter, inject, Input, OnInit, Output } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatRadioModule } from '@angular/material/radio';

enum ToolPurpose {
  CustomerEngagement = 'Customer Engagement',
  InternalDemo = 'Internal Demo',
  TestingAndExperimentation = 'Testing and Experimentation',
}

export interface ProjectDetails {
  toolPurpose?: ToolPurpose;
  customerName?: string;
  projectName?: string;
  description?: string;
}

@Component({
  selector: 'app-project-details-form',
  standalone: true,
  imports: [
    MatFormFieldModule,
    MatRadioModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatInputModule,
    NgIf,
  ],
  templateUrl: './project-details-form.component.html',
  styleUrl: './project-details-form.component.scss',
})
export class ProjectDetailsFormComponent implements OnInit {
  @Input() projectDetails?: ProjectDetails;
  @Output() projectDetailsEvent = new EventEmitter<any>();

  private readonly formBuilder = inject(FormBuilder);

  projectDetailsFormGroup = this.formBuilder.group({
    toolPurpose: [null as ToolPurpose | null, Validators.required],
    customerName: [''],
    projectName: [''],
    description: [''],
  });

  get customerNameCtrl() {
    return this.projectDetailsFormGroup.get('customerName');
  }

  get projectNameCtrl() {
    return this.projectDetailsFormGroup.get('projectName');
  }

  get toolPurpose(): ToolPurpose | undefined | null {
    return (
      this.projectDetailsFormGroup.get('toolPurpose')?.value
    );
  }

  toolPurposeEnum = ToolPurpose;

  ngOnInit(): void {
    if (this.projectDetails) {
      this.projectDetailsFormGroup.patchValue(this.projectDetails);
      this.onToolPurposeChange(this.projectDetails.toolPurpose);
    }
  }

  onToolPurposeChange(value?: ToolPurpose) {
    if (value && value === ToolPurpose.CustomerEngagement) {
      this.customerNameCtrl?.setValidators([Validators.required]);
      this.projectNameCtrl?.setValidators([Validators.required]);
    } else {
      this.customerNameCtrl?.clearValidators();
      this.projectNameCtrl?.clearValidators();
    }
    this.customerNameCtrl?.updateValueAndValidity();
    this.projectNameCtrl?.updateValueAndValidity();
  }

  onNext() {
    this.projectDetailsEvent.emit(this.projectDetailsFormGroup.value);
  }
}
