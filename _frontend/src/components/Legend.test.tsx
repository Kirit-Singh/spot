import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { EVIDENCE } from '../design/tokens'
import { Legend } from './Legend'

test('renders every evidence type in the legend', () => {
  render(<Legend />)
  for (const key of Object.keys(EVIDENCE)) {
    expect(screen.getByText(key)).not.toBeNull()
  }
})
