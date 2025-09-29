import { Component, OnInit } from '@angular/core';
import { CardData } from '../../../card-data.interface'; // Adjust path
import { CardComponent } from '../card/card.component';
import { NgFor } from '@angular/common';
import { fadeSlideIn, staggerFade } from '../../utils/animations';

@Component({
  selector: 'app-card-list',
  templateUrl: './card-list.component.html',
  styleUrls: ['./card-list.component.scss'],
  standalone: true,
  imports: [CardComponent, NgFor],
  animations: [fadeSlideIn, staggerFade],
})
export class CardListComponent implements OnInit {
  cards: CardData[] = [];

  ngOnInit(): void {
    // Sample Data
    this.cards = [
      {
        imageUrl: 'assets/images/automation-image-3.png',
        title: 'CES Multilingual Agent',
        description:
          'Effortlessly create multilingual Dialogflow CX agents, including Generative AI features, with our automated Translation Tool. Simply input your source agent and desired languages to generate fully translated, functional agents instantly. Slash development time, eliminate manual translation errors, gain flexibility with selective feature translation, and accelerate your global deployment.',
        buttonText: 'Open Tool',
        routePath: '/multilingual-agent',
        demoVideoUrl: 'https://drive.google.com/file/d/1rD_rc_uxUhDuN6Vuubgu-oU3ZDsZXiyj/preview',
        caseStudyUrl: 'https://docs.google.com/presentation/d/1-QjKWxhdk-AIjZFYUWGAEsIOCobJNe3Q0RmZXP_pUiQ/edit?slide=id.g355407d3a6b_2_0&resourcekey=0-MOd-Z7FqyMJgqozwFDu3fg#slide=id.g355407d3a6b_2_0',
      },
      {
        imageUrl: 'assets/images/automation-image-2.png',
        title: 'CES Insights',
        description:
          'Unlock powerful CES Insights, including advanced GenAI features, for your existing Twilio conversation data. Our automated Terraform connector deploys data pipelines to seamlessly ingest, transform (into the required JSON format), and load your Twilio transcripts into GCS for analysis. Effortlessly bridge the data gap, eliminate complex manual setup, and rapidly accelerate the adoption and time-to-value of CES Insights for non-CES users.',
        buttonText: 'Open Tool',
        routePath: '/insights-agent',
        demoVideoUrl: 'https://drive.google.com/file/d/1h6YZOEqtSmewZlknyaExjmeuAJ0gRSVK/preview', // Could not find a video for this card so using a different one
        caseStudyUrl: 'https://docs.google.com/presentation/d/1-QjKWxhdk-AIjZFYUWGAEsIOCobJNe3Q0RmZXP_pUiQ/edit?slide=id.g355407d3a6b_2_78&resourcekey=0-MOd-Z7FqyMJgqozwFDu3fg#slide=id.g355407d3a6b_2_78',
      },
      {
        imageUrl: 'assets/images/automation-image-3.png',
        title: 'CES FBL Analytics',
        description:
          'Unlock instant insights into your Contact Center AI performance with our automated Analytics Framework. This ready-to-use dashboard solution leverages BigQuery exports to deliver standardized KPIs, eliminating redundant custom builds. Accelerate agent optimization, save development time, and provide consistent, actionable conversation analysis across all your CES projects.',
        buttonText: 'Open Tool',
        routePath: '/analytics-agent',
        demoVideoUrl: 'https://drive.google.com/file/d/18booNl-tz5a1-VD5_JTaXU5I8zA085Cc/preview',
        caseStudyUrl: 'https://docs.google.com/presentation/d/1-QjKWxhdk-AIjZFYUWGAEsIOCobJNe3Q0RmZXP_pUiQ/edit?slide=id.g355407d3a6b_2_52&resourcekey=0-MOd-Z7FqyMJgqozwFDu3fg#slide=id.g355407d3a6b_2_52',
      },
      {
        imageUrl: 'assets/images/automation-image-1.png',
        title: 'CES Foundations',
        description:
          ' Eliminate costly delays in your CES implementations caused by incorrect GCP/CES setup. Our Foundation Validator CLI automatically verifies all prerequisites – projects, APIs, security, networking – for your Dialogflow/Agent Assist configuration. Instantly pinpoint all foundational gaps and receive auto-generated Terraform scripts for rapid correction, ensuring a smooth, error-free Open Tool to your CES projects.',
        buttonText: 'Open Tool',
        routePath: '/foundation',
        demoVideoUrl: 'https://drive.google.com/file/d/1iNX580_kZgwYHGrXzKG86g-WHPCFy5Ki/preview',
        caseStudyUrl: 'https://docs.google.com/presentation/d/1-QjKWxhdk-AIjZFYUWGAEsIOCobJNe3Q0RmZXP_pUiQ/edit?slide=id.g355407d3a6b_1_82&resourcekey=0-MOd-Z7FqyMJgqozwFDu3fg#slide=id.g355407d3a6b_1_82',
      },
      {
        imageUrl: 'assets/images/automation-image-4.png',
        title: 'CES Design Automation',
        description:
          'Convert your visual conversational designs directly into Dialogflow CX agents automatically. Our tool reads diagrams from Visio, Lucidchart, and more, creating all necessary components instantly. Slash development time, ensure fidelity, and streamline both new builds and legacy migrations.',
        buttonText: 'Open Tool',
        routePath: '/design-automation',
        demoVideoUrl: 'https://drive.google.com/file/d/10Mdkq5dB3ysTrypIA0DKE6UF2xl-n4Fm/preview',
        caseStudyUrl: 'https://docs.google.com/presentation/d/1-QjKWxhdk-AIjZFYUWGAEsIOCobJNe3Q0RmZXP_pUiQ/edit?slide=id.g355407d3a6b_2_65&resourcekey=0-MOd-Z7FqyMJgqozwFDu3fg#slide=id.g355407d3a6b_2_65',
      },
    ];
  }
}
