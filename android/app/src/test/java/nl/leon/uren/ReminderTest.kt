package nl.leon.uren

import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.LocalDateTime

class ReminderTest {
    @Test fun zelfdeDagVoorAchtUur() {
        // vrijdag 30-10-2026 15:00 -> vandaag 20:00
        assertEquals(LocalDateTime.of(2026, 10, 30, 20, 0), Reminder.nextTrigger(LocalDateTime.of(2026, 10, 30, 15, 0), 20, 0))
    }

    @Test fun naAchtUurVolgendeDag() {
        // vrijdag 21:00 -> zaterdag 20:00
        assertEquals(LocalDateTime.of(2026, 10, 31, 20, 0), Reminder.nextTrigger(LocalDateTime.of(2026, 10, 30, 21, 0), 20, 0))
    }

    @Test fun zondagWordtOvergeslagen() {
        // zaterdag 20:00 precies -> maandag 20:00
        assertEquals(LocalDateTime.of(2026, 11, 2, 20, 0), Reminder.nextTrigger(LocalDateTime.of(2026, 10, 31, 20, 0), 20, 0))
        // zondag middag -> maandag
        assertEquals(LocalDateTime.of(2026, 11, 2, 20, 0), Reminder.nextTrigger(LocalDateTime.of(2026, 11, 1, 12, 0), 20, 0))
    }
}

class DayTest {
    @Test fun factorTeltMee() {
        val d = Day(java.time.LocalDate.of(2026, 11, 1), hours = 4.0, factor = 2.0)
        assertEquals(8.0, d.weighted, 0.0)
    }

    @Test fun urenOpmaak() {
        assertEquals("10,5", fmtHours(10.5))
        assertEquals("8", fmtHours(8.0))
        assertEquals(7.25, parseHours("7,25")!!, 0.0)
    }
}

class PairLinkTest {
    @Test fun leestUrlEnToken() {
        val p = parsePairLink("uren://koppel?url=https%3A%2F%2Furen.example.nl%2F&token=abc-123_x")
        assertEquals("https://uren.example.nl" to "abc-123_x", p)
    }

    @Test fun weigertAndereLinks() {
        assertEquals(null, parsePairLink("https://evil.example/koppel?url=https://x&token=y"))
        assertEquals(null, parsePairLink("uren://koppel?url=ftp%3A%2F%2Fx&token=y"))
        assertEquals(null, parsePairLink("uren://koppel?url=https%3A%2F%2Fx"))
        assertEquals(null, parsePairLink(null))
    }
}
