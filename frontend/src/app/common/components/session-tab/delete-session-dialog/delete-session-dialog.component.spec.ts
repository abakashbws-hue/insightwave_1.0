import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DeleteSessionDialogComponent } from './delete-session-dialog.component';

describe('DeleteSessionDialogComponent', () => {
  let component: DeleteSessionDialogComponent;
  let fixture: ComponentFixture<DeleteSessionDialogComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DeleteSessionDialogComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(DeleteSessionDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
