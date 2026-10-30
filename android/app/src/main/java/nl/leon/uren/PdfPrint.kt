package nl.leon.uren

import android.content.Context
import android.os.Bundle
import android.os.CancellationSignal
import android.os.ParcelFileDescriptor
import android.print.PageRange
import android.print.PrintAttributes
import android.print.PrintDocumentAdapter
import android.print.PrintDocumentInfo
import android.print.PrintManager
import java.io.File
import java.io.FileOutputStream

/** Stuurt een PDF naar de Android-printdienst (printer, of 'Opslaan als PDF'). */
fun printPdf(context: Context, file: File, jobName: String) {
    val adapter = object : PrintDocumentAdapter() {
        override fun onLayout(
            old: PrintAttributes?, new: PrintAttributes, cancel: CancellationSignal,
            callback: LayoutResultCallback, extras: Bundle?,
        ) {
            if (cancel.isCanceled) return callback.onLayoutCancelled()
            callback.onLayoutFinished(
                PrintDocumentInfo.Builder(file.name).setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).build(),
                true,
            )
        }

        override fun onWrite(
            pages: Array<out PageRange>, dest: ParcelFileDescriptor, cancel: CancellationSignal,
            callback: WriteResultCallback,
        ) {
            try {
                file.inputStream().use { inp -> FileOutputStream(dest.fileDescriptor).use { inp.copyTo(it) } }
                callback.onWriteFinished(arrayOf(PageRange.ALL_PAGES))
            } catch (e: Exception) {
                callback.onWriteFailed(e.message)
            }
        }
    }
    context.getSystemService(PrintManager::class.java).print(jobName, adapter, PrintAttributes.Builder().build())
}
