import { NextRequest, NextResponse } from 'next/server';
import { createRouteHandlerClient } from '@supabase/auth-helpers-nextjs';
import { cookies } from 'next/headers';
import { Database } from '@/types/database';

export async function POST(request: NextRequest) {
  try {
    const supabase = createRouteHandlerClient<Database>({ cookies });

    // Get all current manholes
    const { data: manholes, error: fetchError } = await supabase
      .from('manhole')
      .select('*')
      .order('id');

    if (fetchError) {
      return NextResponse.json({
        success: false,
        error: 'Failed to fetch manholes',
        details: fetchError.message
      }, { status: 500 });
    }

    if (!manholes || manholes.length === 0) {
      return NextResponse.json({
        success: false,
        error: 'No manholes found to update'
      }, { status: 404 });
    }

    const updatePromises = manholes.map(async (manhole) => {
      // Create new title format: "原title+ID"
      const newTitle = `${manhole.title}+${manhole.id}`;

      // Create detail URL based on manhole ID
      const detailUrl = `https://pokefuta-tracker.example.com/manhole/${manhole.id}`;

      // Set current timestamp for source_last_checked
      const sourceLastChecked = new Date().toISOString();

      return supabase
        .from('manhole')
        .update({
          title: newTitle,
          detail_url: detailUrl,
          source_last_checked: sourceLastChecked
        })
        .eq('id', manhole.id)
        .select();
    });

    const results = await Promise.all(updatePromises);

    // Check for errors in any update
    const errors = results.filter(result => result.error);
    if (errors.length > 0) {
      return NextResponse.json({
        success: false,
        error: 'Some updates failed',
        failed_updates: errors.length,
        total_attempts: results.length,
        errors: errors.map(e => e.error?.message)
      }, { status: 500 });
    }

    // Count successful updates
    const successfulUpdates = results.filter(result => result.data && result.data.length > 0);

    return NextResponse.json({
      success: true,
      message: `Successfully updated ${successfulUpdates.length} manholes`,
      updated_count: successfulUpdates.length,
      total_manholes: manholes.length,
      sample_updates: successfulUpdates.slice(0, 3).map(result => ({
        id: result.data?.[0]?.id,
        old_title: manholes.find(m => m.id === result.data?.[0]?.id)?.title,
        new_title: result.data?.[0]?.title,
        detail_url: result.data?.[0]?.detail_url,
        source_last_checked: result.data?.[0]?.source_last_checked
      }))
    });

  } catch (error) {
    console.error('Update error:', error);
    return NextResponse.json({
      success: false,
      error: 'Unexpected error during update',
      details: error.message
    }, { status: 500 });
  }
}

export async function GET(request: NextRequest) {
  try {
    const supabase = createRouteHandlerClient<Database>({ cookies });

    const { data: manholes, error } = await supabase
      .from('manhole')
      .select('id, title, detail_url, source_last_checked')
      .order('id')
      .limit(10);

    if (error) {
      return NextResponse.json({
        success: false,
        error: error.message
      }, { status: 500 });
    }

    return NextResponse.json({
      success: true,
      sample_manholes: manholes,
      total_shown: manholes?.length || 0,
      format_info: {
        title_format: "原title+ID",
        detail_url_format: "https://pokefuta-tracker.example.com/manhole/{id}",
        source_last_checked_format: "ISO timestamp"
      }
    });

  } catch (error) {
    return NextResponse.json({
      success: false,
      error: error.message
    }, { status: 500 });
  }
}