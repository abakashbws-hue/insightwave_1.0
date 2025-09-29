import { Component } from '@angular/core';
import { HeaderComponent } from '../common/components/header/header.component';
import { HeroSectionComponent } from '../common/components/hero-section/hero-section.component';
import { CardListComponent } from '../common/components/card-list/card-list.component';
import { FooterComponent } from '../common/components/footer/footer.component';

@Component({
  selector: 'app-landing-page',
  templateUrl: './landing-page.component.html',
  styleUrl: './landing-page.component.scss',
  standalone: true,
  imports: [
    HeaderComponent,
    HeroSectionComponent,
    CardListComponent,
    FooterComponent,
  ],
})
export class LandingPageComponent {}
