// Canonical reusable-arm identity. The physically-identical computation for a program +
// desired change + condition is shared across selections regardless of which ROLE
// (away_from_A / toward_b) it plays, so the key must be by DESIRED_CHANGE, never by role or
// by the pole's high|low direction. The pole direction is preserved separately in the
// selection; here we only derive the reuse key.
//
// desired_change table (role × pole direction):
//   away_from_A(high)=decrease  away_from_A(low)=increase
//   toward_b(high)=increase     toward_b(low)=decrease

import { describe, expect, it } from 'vitest';
import {
  desiredChange,
  directArmKey,
  pathwayArmKey,
  temporalArmKey,
  convergenceKey,
} from '../armKey';

describe('desiredChange — all four role × pole combinations', () => {
  it('away_from_A(high) = decrease', () => {
    expect(desiredChange('away_from_A', 'high')).toBe('decrease');
  });
  it('away_from_A(low) = increase', () => {
    expect(desiredChange('away_from_A', 'low')).toBe('increase');
  });
  it('toward_b(high) = increase', () => {
    expect(desiredChange('toward_b', 'high')).toBe('increase');
  });
  it('toward_b(low) = decrease', () => {
    expect(desiredChange('toward_b', 'low')).toBe('decrease');
  });

  it('the same high pole means OPPOSITE desired changes by role (never key by high|low)', () => {
    expect(desiredChange('away_from_A', 'high')).not.toBe(desiredChange('toward_b', 'high'));
  });
});

describe('canonical reusable arm keys use desired_change, not role/high|low', () => {
  it('direct: direct|program_id|desired_change|condition', () => {
    expect(directArmKey('naive_like', 'decrease', 'Rest')).toBe('direct|naive_like|decrease|Rest');
  });

  it('pathway: appends the gene-set source', () => {
    expect(pathwayArmKey('naive_like', 'decrease', 'Rest', 'reactome')).toBe(
      'pathway|naive_like|decrease|Rest|reactome',
    );
  });

  it('temporal: temporal|program_id|desired_change|from|to', () => {
    expect(temporalArmKey('naive_like', 'increase', 'Rest', 'Stim48hr')).toBe(
      'temporal|naive_like|increase|Rest|Stim48hr',
    );
  });

  it('two roles that both want (program, decrease, condition) collapse to ONE direct key (reuse)', () => {
    // away_from_A on a high-A pole => decrease; toward_b on a low-B pole => decrease
    const kA = directArmKey('checkpoint_hi', desiredChange('away_from_A', 'high'), 'Rest');
    const kB = directArmKey('checkpoint_hi', desiredChange('toward_b', 'low'), 'Rest');
    expect(kA).toBe(kB);
    expect(kA).toBe('direct|checkpoint_hi|decrease|Rest');
  });

  it('convergence is shared per (condition, source): 6 artifacts, each referenced by 20 enrichment arms', () => {
    const conditions = ['Rest', 'Stim8hr', 'Stim48hr'];
    const sources = ['reactome', 'go_bp'];
    const convergence = new Set<string>();
    for (const c of conditions) for (const s of sources) convergence.add(convergenceKey(c, s));
    expect(convergence.size).toBe(6);
    // the 20 enrichment arms of one (condition, source) all map to ONE convergence key
    const programs = Array.from({ length: 10 }, (_, i) => `program_${i}`);
    const armsForRestReactome = new Set<string>();
    for (const p of programs) {
      for (const dc of ['increase', 'decrease'] as const) {
        armsForRestReactome.add(pathwayArmKey(p, dc, 'Rest', 'reactome'));
      }
    }
    expect(armsForRestReactome.size).toBe(20);
    expect(convergenceKey('Rest', 'reactome')).toBe('convergence|Rest|reactome');
  });

  it('same program + same high pole across DIFFERENT time pairs → distinct temporal keys, shared program/desired_change', () => {
    const dc = desiredChange('away_from_A', 'high'); // decrease
    const k1 = temporalArmKey('checkpoint_hi', dc, 'Rest', 'Stim8hr');
    const k2 = temporalArmKey('checkpoint_hi', dc, 'Rest', 'Stim48hr');
    const k3 = temporalArmKey('checkpoint_hi', dc, 'Stim8hr', 'Rest'); // reversed direction
    expect(new Set([k1, k2, k3]).size).toBe(3);
    expect(k1.startsWith('temporal|checkpoint_hi|decrease|')).toBe(true);
    expect(k3).toBe('temporal|checkpoint_hi|decrease|Stim8hr|Rest');
  });
});
