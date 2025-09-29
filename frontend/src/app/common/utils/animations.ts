import {
  animate,
  style,
  transition,
  trigger,
  query,
  stagger,
} from '@angular/animations';

export const fadeSlideIn = trigger('fadeSlideIn', [
  transition(':enter', [
    style({ opacity: 0, transform: 'translateY(20px)' }),
    animate(
      '500ms ease-out',
      style({ opacity: 1, transform: 'translateY(0)' })
    ),
  ]),
]);

export const fadeIn = trigger('fadeIn', [
  transition(':enter', [
    style({ opacity: 0 }),
    animate('1000ms ease-out', style({ opacity: 1 })),
  ]),
]);

export const fadeInFromLeftAnimation = trigger('fadeInFromLeft', [
  transition(':enter', [
    style({
      opacity: 0,
      transform: 'translateX(-30px)'
    }),
    animate('300ms ease-out', style({
      opacity: 1,
      transform: 'translateX(0)'
    }))
  ]),
  transition(':leave', [
    animate('300ms ease-in', style({
      opacity: 0,
      transform: 'translateX(-30px)'
    }))
  ])
]);

export const staggerFade = trigger('staggerFade', [
  transition('* => *', [
    query(
      ':enter',
      [
        style({ opacity: 0, transform: 'translateY(30px)' }),
        stagger('100ms', [
          animate(
            '500ms ease-out',
            style({ opacity: 1, transform: 'translateY(0)' })
          ),
        ]),
      ],
      { optional: true }
    ),
  ]),
]);

export const fadeInOutAnimation = trigger('fadeInOut', [
  transition(':enter', [
    style({ opacity: 0 }),
    animate('300ms ease-out', style({ opacity: 1 })),
  ]),
  transition(':leave', [
    animate('300ms ease-in', style({ opacity: 0 })),
  ]),
]);

export const slideUpDownAnimation = trigger('slideUpDown', [
  transition(':enter', [
    style({ transform: 'translateY(100%)', opacity: 0 }),
    animate('400ms cubic-bezier(0.4, 0, 0.2, 1)', style({ transform: 'translateY(0)', opacity: 1 })),
  ]),
  transition(':leave', [
    animate('400ms cubic-bezier(0.4, 0, 0.2, 1)', style({ transform: 'translateY(100%)', opacity: 0 })),
  ]),
]);

export const slideInOutAnimation = trigger('slideInOut', [
  transition(':enter', [
    style({ transform: 'translateY(20px)', opacity: 0 }),
    animate('400ms cubic-bezier(0.4, 0, 0.2, 1)', style({ transform: 'translateY(0)', opacity: 1 })),
  ]),
  transition(':leave', [
    animate('400ms cubic-bezier(0.4, 0, 0.2, 1)', style({ transform: 'translateY(-20px)', opacity: 0 })),
  ]),
]);

export const messageAnimation = trigger('messageAnimation', [
  transition(':enter', [
    style({ transform: 'translateY(20px)', opacity: 0 }),
    animate('300ms cubic-bezier(0.4, 0, 0.2, 1)', style({ transform: 'translateY(0)', opacity: 1 })),
  ]),
]);
