import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-quickstart',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './quickstart.component.html',
  styleUrls: ['./quickstart.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class QuickstartComponent {}
