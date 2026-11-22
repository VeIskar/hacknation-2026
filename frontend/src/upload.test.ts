import { describe, expect, it } from 'vitest'
import { ACCEPT_ATTRIBUTE, MAX_NAME_LENGTH, MSG_EMPTY, MSG_NAME, MSG_TOO_LARGE, MSG_TYPE, fileProblem } from './upload.ts'

const file = (name: string, size = 1000) => ({ name, size })

describe('fileProblem', () => {
  it('przepuszcza każdy z 8 formatów, bez względu na wielkość liter', () => {
    for (const name of ['a.pdf', 'b.DOC', 'c.docx', 'd.ods', 'e.XLSX', 'f.jpg', 'g.jpeg', 'h.JPE', 'i.png']) {
      expect(fileProblem(file(name)), name).toBeNull()
    }
  })

  it('odrzuca inne rozszerzenia i plik bez rozszerzenia tekstem z API', () => {
    expect(fileProblem(file('wniosek.txt'))).toBe(MSG_TYPE)
    expect(fileProblem(file('wniosek'))).toBe(MSG_TYPE)
    expect(fileProblem(file('wniosek.pdf.exe'))).toBe(MSG_TYPE)
  })

  it('odrzuca znaki zakazane w SPEC i znaki sterujące w nazwie', () => {
    for (const char of [';', ':', '>', '<', '/', '\\', '|', "'", '*', '%', '$', '\u0007']) {
      expect(fileProblem(file(`wniosek${char}1.pdf`)), JSON.stringify(char)).toBe(MSG_NAME)
    }
  })

  it('przyjmuje nazwę do 250 znaków i odrzuca dłuższą', () => {
    const stem = (length: number) => 'a'.repeat(length - 4)
    expect(fileProblem(file(`${stem(MAX_NAME_LENGTH)}.pdf`))).toBeNull()
    expect(fileProblem(file(`${stem(MAX_NAME_LENGTH + 1)}.pdf`))).toBe(MSG_NAME)
  })

  it('pilnuje limitu 10 MB i pustego pliku', () => {
    expect(fileProblem(file('a.pdf', 10 * 1024 * 1024))).toBeNull()
    expect(fileProblem(file('a.pdf', 10 * 1024 * 1024 + 1))).toBe(MSG_TOO_LARGE)
    expect(fileProblem(file('a.pdf', 0))).toBe(MSG_EMPTY)
  })

  it('sprawdza nazwę przed rozmiarem i typem, jak API', () => {
    expect(fileProblem(file('a;b.txt', 50 * 1024 * 1024))).toBe(MSG_NAME)
    expect(fileProblem(file('a.txt', 50 * 1024 * 1024))).toBe(MSG_TOO_LARGE)
  })

  it('pole wyboru pliku podpowiada te same rozszerzenia', () => {
    expect(ACCEPT_ATTRIBUTE).toBe('.pdf,.doc,.docx,.ods,.xlsx,.jpg,.jpeg,.jpe,.png')
  })
})
