import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PendingEventDialogComponent } from './pending-event-dialog.component';

describe('PendingEventDialogComponent', () => {
  let component: PendingEventDialogComponent;
  let fixture: ComponentFixture<PendingEventDialogComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PendingEventDialogComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(PendingEventDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
