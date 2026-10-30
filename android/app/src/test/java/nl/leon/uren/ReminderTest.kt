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

class HolidayTest {
    @Test fun pasenEnFeestdagenZelfdeAlsServer() {
        assertEquals(java.time.LocalDate.of(2026, 4, 5), HolidayCalc.easter(2026))
        assertEquals(java.time.LocalDate.of(2025, 4, 20), HolidayCalc.easter(2025))
        val h = HolidayCalc.defaults(2026).associate { it.name to it.date.toString() }
        assertEquals("2026-04-27", h["Koningsdag"])
        assertEquals("2026-05-14", h["Hemelvaartsdag"])
        assertEquals("2026-05-25", h["2e Pinksterdag"])
        assertEquals("2025-04-26", HolidayCalc.defaults(2025).first { it.name == "Koningsdag" }.date.toString())
    }

    @Test fun ontbrekendeDag() {
        val today = java.time.LocalDate.of(2026, 10, 30)
        val first = java.time.LocalDate.of(2026, 1, 1)
        val di = Day(java.time.LocalDate.of(2026, 10, 27))
        assertEquals(true, isMissing(di, first, null, today))
        assertEquals(false, isMissing(di.copy(vakantie = 1.0), first, null, today))
        assertEquals(false, isMissing(Day(java.time.LocalDate.of(2026, 10, 25)), first, null, today)) // zondag
        assertEquals(false, isMissing(Day(today), first, null, today)) // vandaag nog niet
    }
}

class TweeHerinneringenTest {
    private val times = listOf(java.time.LocalTime.of(20, 0), java.time.LocalTime.of(21, 30))

    @Test fun naEersteKomtTweede() {
        assertEquals(LocalDateTime.of(2026, 10, 30, 21, 30),
            Reminder.nextTrigger(LocalDateTime.of(2026, 10, 30, 20, 1), times))
    }

    @Test fun feestdagWordtOvergeslagen() {
        // za 31-10 overslaan (pretend feestdag), zondag sowieso -> maandag 20:00
        val skip = { d: java.time.LocalDate -> d == java.time.LocalDate.of(2026, 10, 31) }
        assertEquals(LocalDateTime.of(2026, 11, 2, 20, 0),
            Reminder.nextTrigger(LocalDateTime.of(2026, 10, 30, 22, 0), times, skip))
    }
}
