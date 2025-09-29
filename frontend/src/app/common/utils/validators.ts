import { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';

export function greaterThanZeroValidator(): ValidatorFn {
  return (control: AbstractControl): ValidationErrors | null => {
    const value = control.value;
    return !isNaN(value) && value !== null && value > 0
      ? null
      : { greaterThanZero: true };
  };
}

export function redactionStepValidator(): ValidatorFn {
  return (control: AbstractControl): ValidationErrors | null => {
    const value = control.value;
    if (value === null || value === undefined || value === '') {
      return null;
    }
    const allowedValues = ['fetch', 'ingest'];
    const isValid = allowedValues.includes(value);
    return isValid
      ? null
      : {
          allowedValues: {
            allowed: [...allowedValues, '(Empty)'],
            actual: value,
          },
        };
  };
}

export function batchSizeValidator(): ValidatorFn {
  return (control: AbstractControl): ValidationErrors | null => {
    const value = control.value;
    return value !== null && value <= 180
      ? null
      : { belowRecommendedValue: true };
  };
}
